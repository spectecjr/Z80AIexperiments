# wolf3d.z80s — design notes

A textured grid maze, Wolfenstein fashion: one ray a screen column, DDA
through a 16×16 map, textured wall columns, double buffered. Three
viewports are generated and all three are verified; the fastest is 256×96
at four pixels a column, 14.8 Hz.

Verified bit-exact against `tests/wolf.py` over 96 camera poses in each
viewport — both the column list the caster produces and every byte of the
buffer the renderer draws.

## The files

| file | |
|---|---|
| `wolf3d.z80s` | the code. Contains no viewport constants |
| `wolfview*.z80s` | **generated.** The viewport, the ray step table, the height ladder and the height tables — all of which must agree with each other. **Assemble before `wolf3d.z80s`** |
| `wolfdata.z80s` | **generated.** What does not care about viewport size: sines, reciprocals, map, textures |
| `tests/mkwolfdata.py` | writes both. `python3 tests/mkwolfdata.py 256x96x4 wide` |
| `tests/wolf.py` | the model, `set_view(w, h, bytes_per_column)` |
| `tests/harness_wolf*.asm` | one per viewport |

`mul8x8_qs.z80s` must be assembled alongside — `w3d_cast` calls `qsmul8`.

## Interface

| symbol | |
|---|---|
| `w3d_init` | build the scaler bank, black both buffers. ~1.8M T-states, once |
| `w3d_frame` | cast, draw, flip |
| `w3d_cast` | fill `w3d_cols` from `(w3d_px, w3d_py, w3d_ang)` |
| `w3d_draw` | draw `w3d_cols` into the back buffer |
| `w3d_px`, `w3d_py` | camera, 8.8 in map cells |
| `w3d_ang` | heading, 0..255 |
| `w3d_cols` | three bytes a ray: half height, texture page, texture column |

## Why this is the opposite of room3d

`room3d.md` explains that a column costs three times what a row costs on a
Z80. A texture puts a different texel in every column, so there are no runs
along a row to find: **the texture forces column order, and the whole job
becomes making a column write cheap.** Measured, per screen byte of a wall:

| | T-states |
|---|---|
| accumulator loop, stepping the texture by a fraction | 72.6 |
| unrolled scaler, texture steps baked in | 22.8 |
| flat column, no texture at all | 18.4 |
| unrolled scaler, four pixels a column | 14.5 |

So texturing costs 4 T-states a byte and column order costs 13 more than a
row would. The scalers exist to turn 72.6 into 22.8.

## The scalers

`w3d_scalgen` writes, at init, a run of unrolled code per wall height on a
ladder, mapping the 32 texels of a texture column onto that many rows:

    LD A,(DE)      the next texel, once per texel rather than once per row
    INC DE
    LD (HL),A      } as many times as this texel is stretched to cover
    ADD HL,BC      } BC being one screen row

At four pixels a column each row is `LD (HL),A / INC L / LD (HL),A /
ADD HL,BC` and BC is a row **less one**, to make up for the `INC`: 29
T-states for two bytes against 18 for one, with the texel fetched once for
both. It also doubles the bank, which is the thing that limits which
viewports fit.

**The ladder is geometric** — every second row while the wall is short,
every eighth while it fills the screen — so the height error stays near 6%
at any distance instead of being negligible near and hopeless far. A
uniform ladder to the same accuracy would need 30K; this one is 3.6K to
5.6K.

## The caster

Two things a ray wants that a Z80 has not got: a division and a multiply.

**The division** is the delta distance — how far along the ray from one
grid line to the next — and it is `w3d_recip`, a table indexed by the ray
component shifted right 7.

**The multiply** is the distance to the *first* grid line, `(f * dd) >> 8`
with f a byte (where the camera sits inside its own cell) and dd sixteen
bits. f is the same for every ray in the frame, so a table of f×i answers
both halves:

    f * dd = 256 * T[dd >> 8] + T[dd & 255]

and the table is built by pushing a running sum onto the stack — 22
T-states an entry. Two of them cost 11,000 T-states a frame and save four
quarter-square multiplies a ray, which would be 76,000. One table lives in
the low 8K (`w3d_txtab`, placed by the assembler), the other at `W3D_TY`.

**The DDA loop.** The map is one page, one byte a cell, so the map pointer
lives in **BC** and a cell test is `LD A,(BC)` at 7 T-states; the two delta
distances are patched into the loop as immediates instead, along with the
step direction (`INC C`/`DEC C`, `ADD A,±16`). Rays average **two steps**
in this maze, so the per-ray setup, not the loop, is the cost.

**The texture coordinate** is one signed 8×8 through `qsmul8`: the hit
point is `pos + dist * ray / 16384`, and `(dist >> 5) * (ray >> 8) >> 1` is
that to within the five bits anyone reads. Both fit in a byte because no
ray in a 16×16 map is longer than the diagonal. The sign is a correction to
the product's high byte (`a*b = a*bu - 256a` when b < 0), not an
abs-then-negate.

**The sweep** is `w3d_pstep`, the camera plane divided by half the ray
count, and it starts half the rays out from the direction. See the bug
below: this must not go back to being a shift.

## Invariants

- **The map must have a solid border.** Nothing bounds checks; a ray that
  escaped would wrap around the page rather than stop.
- `w3d_sin`, `w3d_recip`, `w3d_pstep`, `w3d_map`, `w3d_hidx`, `w3d_htab`,
  the textures, `w3d_scal`, `w3d_txtab` and `W3D_TY` are all page-aligned
  and indexed as such.
- `w3d_hidx` holds **two** tables in one page: half height → rung in the
  low half, rung → top screen row at +128. So `W3D_NLAD ≤ 128` and
  `W3D_HALF < 128`. The top row is indexed **by rung**, not by height —
  that is what lets them share a page.
- The hit code reads the patched immediates back (`w3d_xa1+1`, `w3d_ya2+1`,
  …) to recover the delta distance. Reordering or renaming those sites
  breaks the distance, silently and only in some views.
- The scaler bank grows with the viewport and has 6,080 bytes before it
  reaches `qsmul8`. **Both ends are checked**: an `ASSERT $ <= 0x2000` in
  each harness for the low 8K, and `tests/test_wolf3d.py` prints what the
  bank has to spare and fails if it overruns. Keep both.
- A texture column is `base + u*32` and u reaches 31, so the product is
  sixteen bits. It overflowed a byte once.

## What it costs

96 poses per viewport, T-states:

|  | 256×144, 128 rays, 2px | 192×96, 96 rays, 2px | 256×96, 64 rays, 4px |
|---|---|---|---|
| `w3d_frame` mean | 712,596 | 453,991 | **405,333** |
| min | 583,453 | 396,709 | 349,814 |
| max | 780,547 | 482,607 | 428,394 |
| at 6 MHz | 8.4 Hz | 13.2 Hz | **14.8 Hz** |
| held to the flyback | 7.6 Hz | 12.1 Hz | 12.5 Hz |
| wall columns | 362,688 (51%) | 211,406 (47%) | 205,693 (51%) |
| `w3d_cast` | 242,138 (34%) | 184,926 (41%) | 127,678 (32%) |
| `w3d_prefill` | 107,656 (15%) | 57,544 (13%) | 71,848 (18%) |
| wall bytes a frame | 14,302 at 25.4 T | 7,376 at 28.7 T | 10,554 at 19.5 T |
| T-states a ray | 1,892 | 1,926 | 1,995 |
| scaler bank | 5,508 | 3,624 | 5,640 |

The three costs divide about the same way in every viewport, so none of
them is the thing to attack alone: the wall bytes are the floor for a
textured wall, the prefill is the floor for anything at all, and the cast
is what is left. A ray costs slightly more in the smaller views only
because the two per-frame tables are shared over fewer rays.

**The prefill** paints the whole viewport ceiling and floor at 5.5
T-states a byte and lets the walls overdraw it, which wastes 78% of what it
writes. Filling only what the walls will not cover needs column-order
writes; on paper — this one is arithmetic, not a measurement — it comes out
about 10,000 T-states ahead in the 256×144 case, which is not worth the
complication.

## Bug history — all of these were real

- **The sweep.** The ray step was `plane >> 6`, which spans the whole
  camera plane only at 128 rays. The 96-ray viewport therefore swept
  −9459..+4506: off centre and a quarter narrow. Now a generated table.
  Anything that changes the ray count must change the step with it.
- **The scaler off-by-one.** Row k must use the texel from *before* the
  accumulator steps. The generator writes then steps.
- **`w3d_htop` was viewport-relative** where it must be absolute screen
  rows.
- **A stale `tests/wolfdata.z80s` shadowed the root one** — sjasmplus
  resolves `INCLUDE` relative to the including file's directory first, and
  `-I` after. Generated data lives in the repo root; do not leave copies in
  `tests/`.
- **The scaler bank overran `qsmul8`'s table** when four-pixel columns
  doubled it. That is what the two checks above are for.

## If you pick this up

**256×144 at four pixels is the combination worth having** — full height,
half the rays, wall bytes at 19.5 T-states — and the arithmetic puts it
near 12.5 Hz. It wants about 9K of scaler and there are only 6K to be had
between the two screen buffers and the stack in a flat 64K map. On a SAM
that can page the bank in, build that.

Smaller, measured, and not taken: the two per-ray table lookups in the
caster are ~8,000 T-states a frame above a split high/low-byte table
layout; the ray-advance tail is ~20 T-states a ray above patched
immediates. Together about 2% — not worth the risk against a working
bit-exact renderer, which is why they are written here instead of done.

    python3 tests/mkwolfdata.py                 # regenerate 256x144
    python3 tests/mkwolfdata.py 192x96 96
    python3 tests/mkwolfdata.py 256x96x4 wide
    python3 tests/test_wolf3d.py                # all three, verify and time
