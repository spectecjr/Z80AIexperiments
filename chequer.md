# chequer.z80s — design notes

A Space Harrier floor: an infinite chequerboard at a fixed camera height,
scrolling both ways, at 50 Hz with a quarter of the frame to spare.

Verified bit-exact against `tests/chequer.py` — every byte of the screen and
every scanline's palette parity — over 28 camera positions.

## Interface

| symbol | |
|---|---|
| `chq_init` | compile the runs, fill both buffers, once |
| `chq_frame` | draw from `(chq_camx, chq_camz)` and flip |
| `chq_out` | the two palette writes a scanline, **for hardware, untested** |
| `chq_camx`, `chq_camz` | the camera, world units; a square is 256 of them |
| `chq_par` | one byte a scanline: which way round the palette goes |

## The one idea

**The depth stripes are not drawn.** With the camera height fixed, one
scanline is one depth, so the board's row parity is constant along it — and
anything constant along a scanline belongs to the palette, not the pixels.
The whole screen is drawn in colour indices 1 and 2, sky included, and what
those two mean is set per scanline.

Two consequences, and they are why this is cheap:

- **Scrolling forward costs nothing in pixels at all.** It moves the
  scanlines at which the palette flips, and nothing else. `chq_par8`, which
  is the entire cost of forward motion, is 7,019 T-states — one 16-bit add
  and a bit test a scanline.
- **Scrolling sideways is a phase**, and the phase as a *fraction of a
  square* is the same at every depth: the camera sits in the same part of a
  square however far away you look. So it is one number a frame, not one a
  scanline.

Since the palette is being written per scanline anyway, the distance fade
comes free — the board grades into the sky colour at the horizon for
nothing, and the sky has its own gradient for nothing.

## One dispatch a scanline

A scanline is a square wave, so it is **one run of alternating `PUSH BC` /
`PUSH DE` with the period baked in** — not one run per square. That is what
stops the cost exploding as the squares shrink to nothing near the horizon:
a scanline costs its 64 `PUSH`es and one dispatch whether it holds four
squares or sixty.

`chq_gen` writes one run per square width at init — i `PUSH`es of one colour
then i of the other, 64 of them plus a cycle, 1,328 bytes for all sixteen —
and the phase is *which push you enter at*.

The awkward part is lining the two up. A run's colour blocks start at its
head; the board's boundaries are fixed to the middle of the screen. The
rightmost `PUSH` covers x = 252..255, so the colour there is
`floor((124 + phi) / p) & 1` — and reading a square wave leftwards rather
than rightwards inverts it, which is half a cycle. That is the whole of

    k = (i - 32 - (phi >> 2)) mod 2i

with `phi >> 2` the high byte of `i * camx`, which accumulates with one add
a period. Get this wrong by one push and the board still looks like a board,
which is why it is checked against the exact perspective formula at every
4-pixel cell on every row, not just eyeballed.

Entering part way in spills the extra pushes off the left hand end into the
row above — so **the floor is drawn bottom upwards**, making the row above
the one drawn next. Only the topmost run's spill needs putting back, which
is `CHQ_SPILL` pushes, generated to match.

## Invariants

- Rows are drawn bottom upwards. Reverse it and every row is corrupted by
  the one below it.
- A row is half a page, so stepping up one is `L ^= 0x80` and a `DEC H` when
  the result is **non**-zero. Inverting that test puts alternate rows 128
  bytes high — which, in the 0x2000 buffer, writes into the 0x8000 one.
  (This was a bug, and it is why the test compares whole buffers.)
- `BC` and `DE` hold the two colours for the whole of `chq_floor` and must
  not be touched: they are what the runs push. The row pointer lives in the
  alternate set for the same reason.
- A square is a whole number of `PUSH`es, so its width and the phase both
  quantise to four pixels. Against an exact model that is invisible — the
  convergence is carried by the palette stripes.
- `chq_ptab`, `chq_ztab`, `chq_fog`, `chq_ent` and `chq_par` are all
  page-aligned and indexed as such.

## What it costs

| | T-states |
|---|---|
| `chq_floor` | 80,480 — 93 scanlines, 865 each |
| `chq_par8` | 7,019 — the palette parities, i.e. all of forward motion |
| `chq_entry` | 3,142 — the sixteen run entry points |
| **`chq_frame`** | **min 90,762, mean 92,404, max 93,216** |
| | **77% of the 120,000 a 50 Hz frame has** |
| `chq_init` | 1,493,036 once, for 1,328 bytes of compiled run |

A scanline is 704 T-states of `PUSH`, 53 of loop, and about 108 of spill.
The first of those is the floor and cannot be beaten; the third is the price
of the phase.

The optimisation pass took it from 103,658 to 92,404: rows come in bands
that share a square width (sixteen of them, generated), so the run and its
entry are worked out once a band rather than once a row, and the row pointer
moved into the alternate register set.

## What is not verified

`chq_frame` writes a parity a scanline into `chq_par`, and all of that is
checked against the model. What the display then does with it — two CLUT
writes in the line interrupt — is **not**, because the test bench is a plain
Z80 with no SAM ASIC in it. `chq_out` is the loop that would run; the raster
timing wants SimCoupe or hardware. Two details to confirm against the manual
first: the CLUT is written through port 248 with the entry index in the high
address byte, and the palette byte is packed `G1 R1 B1 BR G0 R0 B0`.

`tests/mkgif.py` applies `chq_par` and `chq_fog` when it writes the GIF —
`copper()` there flattens the per-scanline palettes into one image — so
`demo/chequer.gif` shows what the screen would show, even though the timing
behind it is unproven.

## If you pick this up

**Scroll sideways by repainting only the edges.** Every scanline is
repainted in full every frame, but sideways motion moves each boundary by a
few pixels: the interiors of the squares do not change. Repainting only the
columns that changed would cut the 80,480 down towards the parity loop's
7,019 — and unlike the current design it would get *cheaper* the slower you
turn. It wants a per-scanline record of where the boundaries were last
frame, and the runs to become variable-length again, which is `room3d`'s
machinery rather than this file's. This is the biggest single win left.

One-pixel phase turned out to be neither expensive nor awkward, and is now
`chequer2.z80s`: four compiled runs per square width instead of one, and a
`PUSH` of a mixed pair wherever a boundary lands inside one. 104,301
T-states against this file's 92,404, and still 50 Hz. Prefer it unless the
5,312 bytes of run are a problem.

    python3 tests/mkchqdata.py      # regenerate the tables
    python3 tests/test_chequer.py   # verify and time
