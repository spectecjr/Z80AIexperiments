# harrier.z80s — design notes

The Space Harrier floor again, with every boundary on its exact pixel.
`chequer.z80s` quantises a square's width and phase to four pixels; this
does not. It costs about twice as much — a 25 Hz routine where the other is
a 50 Hz one — so **keep both**.

> **`chequer3.z80s` now draws this same screen, bit for bit, in half the
> time** — 110,806 T-states against 221,451 — by going back to a compiled
> run a scanline and finding room for the exact width in it. Prefer it
> unless its 12K of run bank is wanted elsewhere. This file is still the
> readable statement of what the board *is*, and its model is what
> chequer3 is tested against.

Verified bit-exact against `tests/harrier.py`, pixels and parities, over 28
camera positions.

## What pixel accuracy costs

A `PUSH` writes two bytes and a byte is two pixels, so a boundary that does
not land on a four-pixel grid has to be carried in the **value** pushed.
`hr_mx` holds, for each of the four offsets and each way round, the pair
with a pixel of each colour in the right place.

So a square is a run of `PUSH`es of one colour followed by one `PUSH` that
straddles the boundary — **a dispatch per square rather than per scanline**.
Three run pages, each 64 `PUSH BC` falling out of the bottom into what comes
next: the boundary push for colour 1, the same for colour 2, and the row
loop for the last square of a line. No returns anywhere.

What is left quantised is nothing. Both the width of a square and the phase
are exact pixels, because they live in `E` and the accumulator rather than
in a compiled run.

## The rest is chequer.z80s

The depth stripes are still the palette's, one parity byte a scanline, and
forward motion still costs nothing in pixels. Read `chequer.md` first — the
geometry, the invariants and the things that are not verifiable here are all
the same.

Two differences worth knowing:

- **Below eight pixels a square gives way to a haze.** At that size the
  board is beyond drawing honestly, and the far field fading to a single
  tone is what distance does anyway. Those rows never change, so `hr_init`
  draws them and the frame does not touch them — which also means the
  square loop can assume at least two `PUSH`es between boundaries.
- **The camera's offset is stepped, not multiplied.** `phi = (camx * p) / 256`
  and `p` grows by at most one pixel a row, so `phi` accumulates in 8.8 with
  one add on the rows where it grows. The row table's top bit says which
  those are. The first row drawn works `phi` out from scratch with one
  `qsmul8` and **must not also step** — it did, once, and the whole board
  drifted a pixel every few rows.

## What it costs

| | T-states |
|---|---|
| `hr_draw` | 214,589 — 84 scanlines, ~2,550 each |
| `hr_par8` | 7,047 |
| **`hr_frame`** | **min 220,394, mean 221,451, max 223,413** |
| | **92% of the 240,000 a 25 Hz frame has** |
| `hr_init` | 1,511,121 once |

59,136 of `hr_draw` is the 64 `PUSH`es a scanline must do whatever happens.
The other 155,000 is about 800 squares at ~190 T-states each, which is what
exactness costs: `chequer` does the same 84 rows for one dispatch each.

The optimisation pass took it from 229,256 — the run dispatch became
`LD H,page / LD L,offset / JP (HL)` instead of a self-modified `JP`, and the
push count is worked out with one subtract instead of a `NEG`.

## If you pick this up

The board's period is fixed per row, so the sequence of (whole pushes,
boundary offset) along a scanline repeats every 4/gcd(p,4) squares. A run
compiled per period covering a whole cycle of squares would cut the dispatch
count by up to four. That is 56 periods at ~100 bytes, which fits where the
scaler bank lives — the reason it is not done is that the phase would go
back to being four-pixel quantised, and pixel accuracy is the entire point
of this file.

The other one, from `chequer.md` and worth more: repaint only the columns a
scroll actually changed.

    python3 tests/mkhrdata.py       # regenerate the tables
    python3 tests/test_harrier.py   # verify and time
