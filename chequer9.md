# chequer9.z80s — design notes

**A horizon that moves.** The ground rises to meet the pilot: the board is
10% of the screen when he is at the bottom of it and half the screen when he
is at the top — Space Harrier's trick — and **one run bank serves all 65
positions of it**. 146,642 T-states a frame on the demo's own path, 193,023
in its worst frame, and 199,930 in the worst frame of the sweep: **83% of a
25 Hz frame**, where the cheapest frames fit inside a 50 Hz one.

| | T-states a frame | |
|---|---|---|
| **the board** | **23,480 … 123,107** | 19 scanlines (10%) to 96 (50%) |
| the swap mask | 522 … 1,754 | copied as far down as the board goes |
| **the desert** | **49,796** | 20 scanlines, two layers, by pixels |
| **the pilot** | **16,116** | 96 rows, anywhere on the screen |
| the sky he left behind | 3,655 … 9,705 | the rows of his old box above the band |
| the rows the board gave up | 0 … 3,736 | when the horizon drops |
| the horizon table and the flip | 542 | |
| **`cq9_frame`** | **90,216 / 146,642 / 193,023** | **25 Hz** |

Bit exact against `tests/chequer9.py` over 130 frames: every one of the 65
horizons twice, walked up the screen and back down, with the camera moving
and the pilot in a different place and a different pose every frame.

## One bank serves every horizon, which is the whole finding

The thing to expect was that a moving horizon meant a set of tables per
horizon, and there is no room for 65 of anything this size. It does not,
and the reason is worth stating plainly:

    a square's width at row y      round(S * (y - horizon) / CAMH)
    a scanline's depth             CAMH * FOCAL / (y - horizon)

Both are functions of **the row's distance from the horizon**, and of
nothing else. A row 40 scanlines below the horizon is the same row whatever
row that is. So the band table — how many scanlines each square width gets —
is one table at every horizon, and a taller board simply **starts further
down it**, at the band holding the bottom row of the screen; the bands
before that one are the ones that would be off the bottom.

What that costs at run time is a table lookup. Five bytes a horizon in
`chequer9hz.z80s`: the chunk to page in, where in that chunk's band table to
start, how many scanlines that is, and the widest square. 542 T-states with
the flip in it — and a 16-bit index, because 65 horizons at five bytes each
is past what a byte will hold.

What it costs in memory is that the board has to be compiled for the
*deepest* board it can ever have. Pitching the horizon up brings coarser
ground into view, so the widest square goes from 64 pixels to 80:
**3,240 compiled bodies in four chunks against chequer8's 2,080 in three**.
That is the real price of a moving horizon and it is paid in pages.

## A horizon is allowed when the bottom row is the last row of its band

A band is drawn whole — one entry into a compiled run, one count — so the
board cannot end in the middle of one. **65 of the 78 rows between 10% and
50% are allowed**: near the horizon a band is a scanline or two, so nearly
every row is, and it is the wide bands at the bottom of the screen that rule
out runs of them. The demo takes the pilot's height, maps it onto those 65
and never asks for a row that is not in the table.

Allowing every row would want a band that can be entered part way *and*
stopped part way, which the runs can do (the desert's already stop where
they should) — but the phase accumulator would then have to start mid-band,
and the saving is one scanline of accuracy in where the ground begins.

## The swap masks do not care where the horizon is

This was the part expected to be the bill. chequer5's swap masks are 512
tables indexed by depth, and the depth of a scanline is exactly what a
moving horizon changes; `chequer8.md` predicted either thousands of
T-states a frame to compute the mask per scanline again, or a set of tables
per horizon step, which does not fit.

Neither. The tables are indexed by *depth*, and the depth of a row is that
same function of `y - horizon` — so they are the tables chequer5 built, only
generated 96 rows deep rather than 77, and **copied as far as the horizon
says**. The copy is 128 `LDI`s entered at `2 * (128 - rows)`:

| | T-states |
|---|---|
| the copy, 19 rows of board | 522 |
| the copy, 96 rows | 1,754 |
| computing the mask a scanline again | 1,539 … 7,776 |

The one thing that genuinely became per-horizon is the phase accumulator's
seed, which is the widest square times the camera — a different square at
every horizon, so six shifts became a shift-and-add multiply of about 100
T-states.

## The pilot walks the stack pointer

chequer8's compiled pilot is 96 rows in 14,401 T-states with every address
in it absolute, which is only possible because he stands still. He moves
now, so `tests/mkjetmove.py` compiles him relative — and on a Z80 that means
`SP`, because it is the only pointer with an add:

| | |
|---|---|
| a run of solid bytes | `PUSH DE` a pair, 5.5 T-states a byte |
| a single byte | `POP BC / LD C,n / PUSH BC` — reads its neighbour and puts it back |
| one pixel of pilot | `POP BC / AND / OR / PUSH BC`, the only read-modify-write left |
| getting there | `LD HL,-d / ADD HL,SP / LD SP,HL`, or `DEC SP` where the step is small |

The whole sprite is **one descending walk of `SP`** from the byte after his
bottom right corner to his top left — rows bottom upwards, bytes right to
left, so every step is a subtraction and the caller's only job is to put
`SP` at the corner. **16,116 T-states against 14,401**, which is 12% for
being able to put him anywhere.

He moves in whole bytes sideways, which is two pixels. A pixel of horizontal
travel would want him compiled at both phases and a mask on every byte of
him rather than 110 of them; at 25 Hz, two pixel steps on a sprite this size
do not read as steps.

## What moves down has to be put back

Everything here is redrawn every frame, so nothing is stale — except where
the picture *shrinks*, because then nothing paints the rows it has given up:

- **the board and the band.** When the horizon drops, the rows between the
  band's old top and its new one are sky now. `cq9_sky` fills them,
  `DUP 64 / PUSH DE` a row — and `PUSH` walks down through memory, which is
  up the screen, which is exactly where those rows are.
- **the pilot.** The box he was in last frame is sky above the band's top
  and painted below it, so `cq9_wipe` puts back only the rows above: 3,655
  to 9,705 T-states over the demo's path, and 11,885 at its ceiling, where
  all 96 of his rows are over sky. The coupling keeps it off that ceiling —
  he is high only when the board is tall — which is worth knowing, because
  it is the one place where the two halves of the demo fight each other.

**Both are per buffer, and that is free.** The paged map keeps a copy of the
resident block behind each screen, so `cq9_seen` and `cq9_ox`/`cq9_oy` are
each buffer's own record of what it was last drawn with — no pair of
variables to keep in step, and a buffer that skipped a horizon step puts
back both of them at once.

## The desert is twenty scanlines, and that is a budget decision

chequer8's band is 32 scanlines and costs 79,758 T-states, which is fine
under a 77-row board and was not under a 114-row one. So chequer9's is 20:
the same two layers, the same picture generator with `DESERT_ROWS` turned
down, the pyramids scaled to the band they are in.

| | T-states a frame | |
|---|---|---|
| the rear layer | 35,866 | 20 rows, compiled, four phases |
| the front layer | 13,930 | 33 spans |
| **`c9_band`** | **49,796** | |

The band rides the horizon: its rows are its own picture and `SP` puts them
wherever the band happens to be, so sliding it up and down the screen costs
nothing at all. That was the prediction in `chequer8.md` and it is the one
part of this that arrived free.

It is also, now, **the largest fixed cost in the frame** — more than twice
the board at the 10% horizon, where the whole frame is 97,620. The board
having become cheap is what leaves 39,000 T-states spare in the worst frame,
and putting the band back up to 26 or 28 scanlines is what that headroom is
for.

## The map

    0,1  2,3  4,5      the board's run bank, the widest bands
    6,7  8,9           the swap mask tables, 512 of them, 96 rows deep
    10,11  12,13       the two buffers, each with the resident code in
                       the 8K a MODE 4 screen leaves at the end of its
                       odd page
    14,15              the rest of the run bank, up to 80 pixel squares
    16,17  18,19       the desert's rear layer, cut by row
    20,21              the pilot, compiled and position independent

Twenty-two of the thirty-two pages `LMPR` can address, so a 512K SAM. The
bank is 95K of compiled bodies, which is what a 256K machine would have to
find somewhere.

## Invariants

- **Every `CALL` must be made with the page its return address is in still
  mapped.** `cq9_pilot` maps his page over the bank and enters the pose with
  `JP (HL)`, not `CALL`; the pose ends `JP CQ9_RET`, which puts the bank
  back. The caller's stack is in chunk 0.
- `SP` is the screen in `cq9_sky`, `cq9_wipe` and the whole of the pilot, so
  all three run with interrupts off and put `SP` back.
- The order is sky, wipe, mask, board, desert, pilot. The board and the band
  paint everything below the band's top, so the two fills only ever touch
  rows above it.
- **A horizon must come from the table.** `cq9_hz` is an index into
  `chq4_hztab`, 0 for the tallest board; the routine never computes a row.
- The mask is copied *before* the board is drawn and is as long as the board
  — `chq4_mskp` points at its last row, because the board is drawn bottom
  upwards.
- Nothing in the resident block may carry state from frame to frame except
  the three cells that are explicitly per buffer.

## What is left

- **The frame varies by a factor of two**, 90,216 to 193,023, which is more
  than anything else here. Held at 25 Hz that is up to 60% of a frame doing
  nothing; the cheap end is inside a 50 Hz frame, so a demo that ran at 50 Hz
  while the pilot was low and dropped to 25 Hz as he climbed would be
  honest — and the line interrupt makes the switch, not a guess.
- **The desert is the fixed cost now.** 49,796 T-states whatever the horizon
  does, against a board that falls to 23,480. Widening the band is the
  obvious thing to spend the headroom on.
- **`cq9_wipe` fills a 16-byte-wide box** and the pilot is drawn over most of
  it a moment later. Filling only the rows he no longer covers would want
  the intersection of two boxes and would save most of the 9,705 it costs
  at its worst on the demo's path.
- **The front layer is still spans at pixel precision**, which is the
  standing decision from chequer8: forcing its offset even would make every
  span whole bytes and save about 5,000 T-states, and would cost the layer
  the thing it was built for.
- **The horizon is the pilot's height and nothing else.** A camera that
  pitched properly would move the board's phase as well, and that is a
  different demo — this one is Space Harrier's fudge on purpose.

    python3 tests/mkchq9data.py               # the board, the desert, the pilot
    python3 tests/desert.py /tmp/desert.png   # look at the layers, 3x
    python3 tests/test_chequer9.py            # verify against the model
