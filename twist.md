# twist.z80s — design notes

A twisting ribbon: a square cross-section turning about a vertical axis,
with the angle stepping down the screen. Two shaded faces, full screen
height, 50 Hz with 15% of the frame to spare.

Verified bit-exact against `tests/twist.py` over 72 angle and twist-rate
combinations.

## Interface

| symbol | |
|---|---|
| `tw_init` | the backdrop into both buffers, once |
| `tw_frame` | draw at `(tw_ang, tw_delta)` and flip |
| `tw_ang` | where the top of the screen sits in `tw_shape` |
| `tw_delta` | how far the whole ribbon is turned |

## Why it is here

It is the opposite of `wolf3d`. Every scanline is three or four horizontal
runs of one colour, and a run goes at 5.5 T-states a byte off the stack
pointer — the one thing this machine is genuinely good at. `wolf3d` pays 25
T-states a byte because a texture forces column order; this pays 5.5.

## The twist is a table

`tw_shape` holds 256 angles — a steady turn with three waves running along
it — laid down twice so 192 scanlines can start anywhere in it and read
straight off the end without wrapping. `tw_ang` picks where the top of the
screen sits in that shape and `tw_delta` turns the whole ribbon, so scrolling
the first sends waves travelling down the ribbon while the second spins it.

It costs 17 T-states a scanline over a constant step, and it is the
difference between a screw and a whip. Anything that fits in 256 bytes and
is periodic is a legal shape.

## The two ideas

**A scanline is one jump.** The whole line — backdrop, left face, right
face, backdrop — is a *single* compiled run of 32 `PUSH`es with the
silhouette baked into which register each one pushes: `HL` for the backdrop,
`BC` and `DE` for the two faces. There is no per-run dispatch at all. A
scanline costs its `PUSH`es plus about 180 T-states of working out which run
it wants.

**There are only 64 runs.** A square looks the same every quarter turn, so
64 silhouettes cover all 256 angles. What changes over a whole turn is which
physical face is on the left and what each is shaded — two table lookups.
2,240 bytes of generated run against 8,960 if the symmetry were ignored.

The colours being three registers is what makes the rest free: the faces
take any shade from the ramp, and the backdrop is one index whose colour the
palette sets per scanline (`chequer.z80s`'s trick), so the gradient behind
the ribbon costs nothing and saves 37 T-states a scanline over reading a
gradient table in the loop.

## Invariants

- `BC`, `DE` and `HL` are the three colours for the whole of `tw_draw`. The
  row pointer, the row counter and the angle live in the **alternate** set
  for that reason.
- `EXX` makes the *other* set active — load the row pointer after it, not
  before. (This was a bug: the pointer went into the shadow, `SP` was set
  from garbage, and the runs pushed over the low 8K.)
- `tw_runlo`, `tw_runhi`, `tw_shl` and `tw_shr` are four **consecutive**
  pages, so one `INC H` walks between them. They must stay in that order and
  each be exactly 256 bytes.
- Corners run anticlockwise, so the corner after the nearest one is to its
  *left*. Getting that backwards makes the visible span run right to left
  and the ribbon disappears.

## What it costs

| | T-states |
|---|---|
| `tw_draw` | 105,603 — 192 scanlines, 550 each |
| **`tw_frame`** | **105,690, and it does not vary** |
| | **88% of the 120,000 a 50 Hz frame has** |
| `tw_init` | 1,428,973 once |

352 of the 550 is the 32 `PUSH`es; the rest is two table lookups, the angle
step and the loop. The optimisation pass took it from 118,107 — the angle
into the alternate set, the backdrop into the palette, and the loop tail
folded into one `EXX`.

The band is 64 bytes — 128 pixels — of the 128-byte line. Widening it costs
11 T-states a byte a scanline, so a full-width ribbon would be about 137,000
T-states and would not hold 50 Hz.

## If you pick this up

Edges quantise to four pixels, because a `PUSH` is two bytes. Two-pixel
edges want a mixed pair at each boundary, which means a fourth register pair
loaded per scanline and the runs knowing where the boundaries are — `room3d`
has the machinery. At this size the stepping does not read, but on a slower
twist it would.

    python3 tests/mktwistdata.py    # regenerate the runs and tables
    python3 tests/test_twist.py     # verify and time
