# chequer9.z80s — design notes

**A horizon that moves, over a board that does not tilt, in sixteen colours
that never change.** The ground rises to meet the pilot — 10% of the screen
when he is at the bottom of it, half the screen when he is at the top — and
the square at the bottom of the screen is the same size at every one of the
78 horizons, because a shallower board is the same picture with scanlines
left out rather than a squeezed copy of it. 141,182 T-states a frame on the
demo's own path, 194,389 in its worst frame, and 191,352 in the worst frame
of the sweep: **81% of a 25 Hz frame, and 109 of the 250 frames in the GIF
fit inside a 50 Hz one.**

| | T-states a frame | |
|---|---|---|
| **the board** | **28,670 … 124,064** | 19 scanlines (10%) to 96 (50%) |
| the swap mask | 1,354 … 6,205 | the deep board's, with the same rows left out |
| **the desert** | **49,796** | 20 scanlines, two layers, by pixels |
| **the pilot** | **8,066** | 24x48, anywhere on the screen |
| the sky he left behind | 1,158 … 5,021 | the rows of his old box above the band |
| the rows the board gave up | 0 … 3,736 | when the horizon drops |
| the horizon table and the flip | 613 | |
| **`cq9_frame`** | **85,994 / 141,182 / 194,389** | **25 Hz** |

Bit exact against `tests/chequer9.py` over 156 frames: every one of the 78
horizons twice, walked up the screen and back down, with the camera moving
and the pilot in a different place and a different pose every frame.

## The board does not tilt: a shallow one leaves scanlines out

The obvious way to move a horizon is to rescale the board into the room it
has — put the camera lower as the horizon drops, so the same picture fits
the fewer scanlines. It is wrong, and it is wrong in a way that is only
obvious once it moves: the squares at the bottom of the screen shrink as the
horizon comes down, and the ground reads as **tilting away** rather than as
being flown over.

So the board is always the same 96 scanline picture — the deepest one the
bank was compiled for — and a lower horizon draws it with rows left out:

    96 scanlines of board    every row of the deep board
    48                       one row in two
    19                       one row in five

which keeps the width at the bottom of the screen at 80 pixels and the width
at the horizon at 1, whatever the horizon is doing. What changes is how much
depth is folded into the screen, which is what flying low over a plane
actually does to it.

**It costs one byte a band and a DDA.** The step through the deep board is
`(96 - 1) * 256 / (n - 1)` in 8.8, and the accumulator starts at half a step
so that both ends land exactly — the top drawn row is the deep board's first
and the bottom one its last, at every horizon. The mask walks the deep
board's own mask table with that step:

| | T-states |
|---|---|
| the mask, 19 rows of board | 1,354 |
| the mask, 96 rows | 6,205 |
| a straight `LDI` copy, when the board was a rescaled one | 522 … 1,754 |

A table is 128 bytes on a 128 byte boundary and the walk is 95 at most, so
the pointer's low byte cannot carry and the gather is ten instructions.

## Which means a band list per horizon

The price is the band tables. A band's compiled bodies and its runs are a
function of its width and of nothing else, so **the 95K bank is still one
bank** — but which bands are drawn is now what a horizon chooses, so each
horizon needs a list of its own: four bytes a band, being the scanlines it
covers, **how many squares wider the band below it was**, and where its
bodies are. That middle byte is what the phase accumulator steps by; it is
one on the deep board and four or five on the shallowest, and the band loop
subtracts `camx` that many times.

    4,105 band entries over all 78 horizons      17K
    3,240 compiled bodies of 30 bytes            95K
    the runs, the value sets, the records        28K

The lists live in the chunk with the bodies they point at, because that is
the chunk the band loop has mapped — so a chunk's terminator carries both
the next chunk and **where this horizon goes on inside it**, and it has to
be read before the `OUT`, not after. That cost an afternoon once already.

**Every row in the range is a horizon now.** The old scheme walked one
shared band table from further down, so the board could only end where a
band did — 65 of 78 rows. A list per horizon has no such rule.

## Nothing here changes a palette entry by scanline

The distance fade on the board and the graded sky were both the palette: two
entries reprogrammed on every scanline, which is what every chequered floor
in this repo has done since `chequer.z80s`. **On a SAM that is a line
interrupt a row** — a palette entry is a port, not memory — and servicing
192 of them costs about a quarter of the frame and needs interrupts enabled,
which a routine drawing through `SP` with the stack pointed at the screen
cannot have.

So chequer9 does without: **one palette, sixteen colours, for the whole
screen and every frame.** The board is two flat greens, the sky is one blue,
and the only depth cue left is the geometry — which turns out to be enough,
because the square sizes and the parity alternation do the work the fade was
decorating.

It costs an index. The board's two colours are 1 and 2 and the sky *was* 1 —
one index meaning sky above the horizon and near ground below it, which only
a per-scanline palette can pull off. With the palette sitting still they
have to be different colours, so the sky is index 15 and `CHQ4_SKYC` comes
with the viewport, alongside what the topmost run spills into.

**What the fade would cost to have back.** Nothing at run time: a band
already chooses its six values from a table, so a band drawn in a different
pair of colours is the same number of T-states. It wants *indices*, and the
count is tight — the pilot has 12 of the 16, the board 2, the sky 1, and
exactly one is spare. One more step of depth colour would fit; a gradient
would want the pilot to give up two or three.

## The pilot is 24x48 now

He is drawn from profiles — a list of (row, left, right) that the rows
between interpolate — so he has a size rather than a bitmap: the numbers
stay in the 32x96 grid they were tuned in and are scaled on the way past,
with spans scaled by their ends so that a four pixel arm at 32 wide is three
pixels at 24 and not two. **8,066 T-states against 16,116**, and a quarter
the pixels.

He is still compiled as **one descending walk of `SP`** — rows bottom
upwards, bytes right to left, so every step is a subtraction and the caller's
only job is to put `SP` at the byte after his bottom right corner:

| | |
|---|---|
| a run of solid bytes | `PUSH DE` a pair, 5.5 T-states a byte |
| a single byte | `POP BC / LD C,n / PUSH BC` — reads its neighbour and puts it back |
| one pixel of pilot | `POP BC / AND / OR / PUSH BC`, the only read-modify-write left |
| getting there | `LD HL,-d / ADD HL,SP / LD SP,HL`, or `DEC SP` where the step is small |

## What moves down has to be put back

Everything here is redrawn every frame, so nothing is stale — except where
the picture *shrinks*, because then nothing paints the rows it has given up:

- **the board and the band.** When the horizon drops, the rows between the
  band's old top and its new one are sky now. `cq9_sky` fills them,
  `DUP 64 / PUSH DE` a row — and `PUSH` walks down through memory, which is
  up the screen, which is exactly where those rows are.
- **the pilot.** The box he was in last frame is sky above the band's top
  and painted below it, so `cq9_wipe` puts back only the rows above: 1,158
  to 5,021 T-states, where a 32x96 pilot cost up to 11,885.

**Both are per buffer, and that is free.** The paged map keeps a copy of the
resident block behind each screen, so `cq9_seen` and `cq9_ox`/`cq9_oy` are
each buffer's own record of what it was last drawn with — no pair of
variables to keep in step, and a buffer that skipped a horizon step puts
back both of them at once.

## The desert is twenty scanlines, and it is the fixed cost now

The same two layers as chequer8, the same picture generator with
`DESERT_ROWS` turned down, the pyramids scaled to the band they are in. The
band rides the horizon for nothing: its rows are its own picture and `SP`
puts them wherever the band happens to be.

| | T-states a frame | |
|---|---|---|
| the rear layer | 35,866 | 20 rows, compiled, four phases |
| the front layer | 13,930 | 33 spans |
| **`c9_band`** | **49,796** | |

At the 10% horizon the whole frame is 89,657 T-states and the desert is
49,796 of it — **more than the board, the pilot and both fills together.**
It is the one thing in the frame that does not know where the horizon is.

## The map

    0,1  2,3  4,5      the board's run bank, the widest bands
    6,7  8,9           the swap mask tables, 512 of them, 96 rows deep
    10,11  12,13       the two buffers, each with the resident code in
                       the 8K a MODE 4 screen leaves at the end of its
                       odd page
    14,15  16,17       the rest of the run bank, up to 80 pixel squares
    18,19  20,21       the desert's rear layer, cut by row
    22,23              the pilot, compiled and position independent

Twenty-four of the thirty-two pages `LMPR` can address, so a 512K SAM.

## Invariants

- **Every `CALL` must be made with the page its return address is in still
  mapped**, and every *table* must be read while its own page still is. The
  band loop reads the next chunk's pointer before the `OUT` that pages that
  chunk in, because afterwards the terminator it is standing on is gone.
- `cq9_pilot` maps his page over the bank and enters the pose with `JP (HL)`,
  not `CALL`; the pose ends `JP CQ9_RET`, which puts the bank back.
- `SP` is the screen in `cq9_sky`, `cq9_wipe` and the whole of the pilot, so
  all three run with interrupts off and put `SP` back.
- The order is sky, wipe, mask, board, desert, pilot. The board and the band
  paint everything below the band's top, so the two fills only ever touch
  rows above it.
- **A horizon must come from the table.** `cq9_hz` is an index into
  `chq4_hztab`, 0 for the tallest board; the routine never computes a row.
- The mask is gathered *before* the board is drawn and is as long as the
  board — `chq4_mskp` points at its last row, because the board is drawn
  bottom upwards.
- Nothing in the resident block may carry state from frame to frame except
  the three cells that are explicitly per buffer.

## What is left

- **The desert is half the shallow frame** and does not vary with the
  horizon. Now that the board falls to 28,670 there is room to widen the
  band back towards chequer8's 32 scanlines — about 2,500 T-states a row.
- **The frame varies by more than a factor of two**, 85,994 to 194,389. The
  cheap end is inside a 50 Hz frame, so a demo that ran at 50 Hz while the
  pilot was low and dropped to 25 Hz as he climbed would be honest, and the
  line interrupt makes that switch rather than a guess.
- **The mask gather is 6,205 T-states at the tall end** where the copy it
  replaced was 1,754. A per-horizon compiled gather would take it back to
  about two thousand, at 78 more little routines in the bank.
- **The front layer is still spans at pixel precision**, which is the
  standing decision from chequer8: forcing its offset even would make every
  span whole bytes and save about 5,000 T-states, and would cost the layer
  the thing it was built for.
- **The horizon is the pilot's height and nothing else.** A camera that
  pitched properly would move the board's phase as well, and that is a
  different demo — this one is Space Harrier's fudge on purpose.

    python3 tests/mkchq9data.py               # the board, the desert, the pilot
    python3 tests/jetpack.py /tmp/pilot.png   # look at him, at whatever size
    python3 tests/test_chequer9.py            # verify against the model
