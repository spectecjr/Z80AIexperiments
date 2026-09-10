# prismpre.z80s — design notes

`prism.z80s` with the whole frame precomputed. **245,608 T-states a frame,
24.4 Hz** — against prism's 493,506 and 12.2 Hz — and the frames are the
same frames: verified byte-for-byte both against `tests/prism.py`'s model
and against `prism.z80s` itself, run side by side at the same turn rates,
over two full times round the loop.

`prism.z80s` is untouched. This is a second routine beside it.

## What is precomputed

Everything in a prism frame that depends on nothing but the frame number:

| | T-states a frame | |
|---|---|---|
| `demo_spin` | 6,628 | the matrix |
| `pr_tables` | 27,649 | nine multiply tables from it |
| `t3d_run` ×7 | 70,597 | 56 vertices rotated, translated, projected |
| `pr_light` | 73,704 | 18 normals shaded and tested against the eye |
| `pr_proj`'s boxes | 13,372 | seven screen boxes |
| `pr_order` | 33,161 | 21 separating planes, then a topological sort |
| | | (the ten buried faces are culled in both, so that saving is prism's too) |
| the rest | ~11,700 | the ramp lookup in `rndl_setface`, and the frame's own box |
| **removed** | **~248,000** | 50% of the frame |

What is left is `rndl_erase` (22,766) and renderlit's span fill (222,841).
There is no multiply anywhere in the frame, and `transform3d.z80s` and
`democube.z80s` are not needed at all — the harness keeps four of their
labels alive (`demo_screen`, `t3d_m`, `t3d_tx/ty/tz`, 31 bytes) because
renderlit's own light and transform paths mention them.

**An exact order is free here.** prism pays 33,161 T-states a frame to
settle which piece is in front of which, by a separating plane per pair
and a topological sort over the pairs that overlap on screen; prismpre
reads the answer out of seven bytes. Both draw the same frames — the test
checks them against each other — so the 3 pairs a loop that the box test
still gets the wrong way round are the same three in both.

## What it costs: the length of the animation

A frame's table is

| | bytes |
|---|---|
| seven pieces of eight `(sx, sy)` | 112 |
| 42 faces of a nibble — the ramp level, bit 3 set if the face is turned away | 21 |
| the pieces, farthest first | 7 |
| the box to erase, in renderlit's four-byte record form | 4 |
| | **144** |

The free RAM is 16K either side of the two screen buffers, less the code.
With transform3d gone that is 2,344 bytes spare in the low 8K after the
records, and 512 above the buffers after the points — so **64 frames fit,
and 68 would not**. The records go low (32 bytes each, stride `f<<5`); the
7,168 bytes of point go at 0xE000 (stride 112, three shifts and two adds).

A 64-frame loop means the spin has to come back to where it started in 64
frames, so every turn rate must be a multiple of four: this is **one turn
an axis per loop**, against prism's two, three and one per 256. At 21.1 Hz
that is a 3.0-second loop, and the logo turns about three times faster than
prism's. That is the whole price. Nothing else about the picture changes.

128 frames would want 18,432 bytes and there are 10,496.

## The one trick worth copying

**`RNDL_LEVELS` is 8, so a ramp level fits in three bits and bit 3 of the
nibble is free.** Visibility rides there rather than in a separate bitmap:
42 faces of level *and* cull in 21 bytes a frame, and unpacking is `AND 8`
for the visibility byte renderlit wants and `AND 7` for the level. That is
384 bytes a loop saved and a bitmap's worth of shifting not done.

Two more:

- **The points are read where they lie.** `rndl_pts` is a pointer, so each
  piece points renderlit straight at its sixteen bytes in the table. Nothing
  is copied into a workspace.
- **The erase box is stored, not computed.** prism walks 56 points a frame
  to find it; here the four bytes go into renderlit's record with an `LDIR`
  of length four.

## What it does not buy

The fill is 91% of what is left, so this is now a rasteriser benchmark, and
it lands **5,608 T-states short of 25 Hz**: 240,000 is the budget and the
mean frame is 245,608, with the minimum at 145,060 and the maximum at
305,889. Most orientations already hold 25 Hz; the broadside ones do not. Fewer, larger pieces would help everywhere;
so would a span fill that pushes constant runs the way `chequer3` does.

## Invariants

- `PP_NF` must divide 256 and every turn rate in `tests/prismpre.py`'s `DA`
  must be `256 / PP_NF` or a multiple, or the loop does not close.
- A ramp level must stay under 8, or it collides with the visibility bit.
- The points table must start on a page boundary only if you change the
  stride arithmetic; as written it does not care.
- The record layout is order (7), box (4), colours (21) — `pp_one` reads the
  colours at `PP_NP + 4`, so a piece count change moves them.

## Running it

    python3 tests/mkprismpredata.py   # regenerate both tables
    python3 tests/prismpre.py         # say how big they are
    python3 tests/test_prismpre.py    # verify against the model and prism
