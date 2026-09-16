# road2.z80s — design notes

**The same road as `road.z80s`, with the palette nailed down, at 50 Hz, and
wider than the screen.**
112,736 T-states a frame — **94% of a 50 Hz frame, worst frame included** —
against `road.z80s`'s 172,141 at 25 Hz.

The camera is flatter than `road.z80s`'s and the road much wider: the
horizon is at row 111, so the road has the bottom **42%** of the screen; it
is **8 pixels across where it meets the horizon and 310 at the bottom**,
which is **121% of the screen**, so it runs off both edges down there. The
centre steers sixty-three pixels either side of the middle, and every row
has a width of its own, so the road's edge steps once a row.

Bit-exact against `tests/road2.py` over 198 frames of a ride. Not a list of
poses: a frame here depends on the two before it, so the test drives a whole
ride and checks every frame of it against the *ideal* picture — which the
routine has to land on however little of it it chose to touch.

| | T-states a frame |
|---|---|
| the compiled runs — the road itself | 45,726 |
| the fills — stale bands, the spill, and the checks for both | 16,795 |
| the geometry — the curvature and the two integrations | 4,415 |
| the row loop and the dispatch, 80 rows | 45,800 |
| the paging | 22 |
| **`rd2_frame`** | **min 104,750, mean 112,736, max 118,270** |

(Differences between measurements of the whole routine with each piece
disabled, not estimates; they sum to the mean. An earlier version of this
table read the runs 5,000 too dear and the fills too cheap, because the
variant it measured had the runs disabled *and* the fills live — and with
no run to move `SP`, the spill repair fires on rows that never spilled.
Disable the fills in both variants and the numbers add up.)

## Why the palette had to go

`road.z80s` puts the mown stripes, the tarmac's bands, the kerb's red and
white and the dashes into the palette, for two bits a scanline, and rides
forward for nothing. That wants a CLUT write every scanline, and it does not
survive contact with this machine twice over.

**It costs more than it saves.** A line-interrupt handler doing four `OUT`s
with its entry and exit is ~150 T-states; over 192 lines that is **28,800 a
frame**, a quarter of a 50 Hz one. What it buys is only the grass stripes —
the other three are *on the road*, which is repainted every frame anyway, so
in pixels they cost a different colour constant and nothing else. And the
grass is worth 11,762, measured (below).

**And it cannot be had at all.** The 5.5 T-states a byte comes from `SP`
pointing at the screen. An interrupt pushes `PC` — into the middle of the
road. So the fill holds `DI` across the whole frame and a per-scanline
copper cannot fire during it. `chequer.md` has the same unresolved conflict
and says so obliquely: the raster timing "wants SimCoupe or hardware".

So: a fixed sixteen-colour palette, everything drawn, and no fade — which
Hang On does not have either.

## Only what moved is repainted

A row's road is **one interval**, which is what makes this work on a road and
not on a chequerboard. The window is the road plus a margin either side, and
everything outside it is already right.

It needs no record of where the road was, which is the part worth keeping:
because the window moves *with* the road, the geometry of a row relative to
its own window never changes, so **every entry in the tables is a constant**
and the only runtime value a whole row needs is where to put `SP`.

**The margin is not slack, it is a speed limit.** It has to cover what the
road moves in the *two* frames a buffer waits its turn — 8 pixels at 20
world units a frame, which is exactly `M`. At 30 it wants 11, at 40 it wants
14. Get this wrong and the road leaves a trail.

## One compiled run a row, and both its ends off the screen

A row's road has a shape fixed by the row — the kerbs are `w/6`, the centre
line `w/10` — and only its *position* moves. So it compiles once and `SP`
places it: `chequer3`'s trick with the road's edges in place of the phase.
At 118% of the screen, though, the window is wider than the row, and a
`PUSH` run cannot be started late or stopped early. The two ends want
different answers:

**The right hand end is entered past.** A run is a mix of one-byte `PUSH
HL`es and four-byte `LD HL,nn / PUSH` pairs, so "skip *n* `PUSH`es" is not
arithmetic — it is a lookup. Each run carries a **stub** per skip, seven
bytes:

    DEFB  the byte the last skipped PUSH would have put at the screen's
          own right hand edge
    LD    HL,what it would have left there
    JP    into the run

so a row is one lookup and a `JP (HL)`. The `LD HL` is the part that is easy
to miss: a run reloads `HL` only where the colour changes, so an entry part
way in can land on a `PUSH` whose `LD` went with the part that was skipped.
Skipping nothing — most rows — needs no stub at all, because a run starts by
loading `HL` itself. The odd byte is stored unconditionally, because where
it was not wanted the run's own first `PUSH` covers it again.

**The left hand end just spills.** `SP` carries on into the previous row,
which is the next one drawn — and lands at *its* right hand end, which its
own window may not reach. So a row puts grass back from there to the
screen's edge before drawing, through the same uniform `PUSH` block a stale
band uses, which unlike the road's run *can* be entered part way in by
arithmetic. That repair is the whole cost of the spill: **3,586 T-states in
the worst frame** of the ride, nothing at all when the road is on screen,
and it never reaches the sky — a row only spills once it is wider than the
rails, which is forty rows below the horizon.

The bank is indexed by (half width, phase, band parity). **Phase is one
pixel**, because `SP` is a byte address and places the road to two pixels on
its own; parity doubles it, because the solid colours could come from
registers but the baked boundary bytes could not. 79 widths — one a row —
make 316 runs and their stubs, **41,297 bytes**.

## Which is why the bank is paged

That 41,297 does not fit in the 15,800 bytes either side of the screen
buffers, and the first version of this squeezed 38 quantised widths into
them instead. Sharing a width between rows is exactly what a staircase is:
the road's edge held its place for two rows in the middle distance and four
or five at the bottom. Quantising more cleverly does not help — the best
schedule that fits is visibly worse, because it buys the middle distance by
spending the bottom.

**The 64K address space is not the memory.** A SAM has 256K in 16K pages,
and `VMPR` points the video hardware at a page directly, so the *displayed*
buffer need not be mapped at all. That leaves:

    0000-7FFF  LMPR: a chunk of the bank, its index tables at the foot
    8000-DFFF  HMPR: the back buffer
    E000-FFFF  this code and its tables, in the 8K a MODE 4 screen leaves
               spare at the end of its odd page, with a copy behind each
               buffer

Rows are drawn widest first and the bank is cut in the same order, so a
frame walks it forwards: **two `OUT`s, 22 T-states, for a bank of any
size.** `.claude/skills/sam-coupe-hardware` has the registers.

The pair rule — the second section of a block is always the page above the
first — means nothing in the address space is permanently mapped once you
page a bank *and* double buffer, so the code is duplicated behind both
buffers. That turned out to **simplify** the routine rather than complicate
it:

- a record's parity mark is *per buffer*, and now there is one copy of the
  records behind each buffer, so the mark is one byte instead of two and
  `rd2_frame` no longer patches the row loop to choose between them;
- `rd2_back` and `rd2_front` went entirely: `HMPR` maps the buffer being
  drawn and `VMPR` says which is shown, so the hardware holds that state
  and the code reads it back;
- the screen is at `0x8000` whichever buffer it is, so the row address is
  a constant.

The caller's stack has to be in the low 32K with chunk 0 paged in, because
the flip swaps this code for its copy — that is the one thing the caller
has to know.

## Which is why the markings survive

`road.z80s` drops a kerb or a centre line below four pixels. That was never
about the marking — it was about the *span machinery*: two boundaries inside
one `PUSH` want a byte carrying three colours, and a mixed-pair table holds
two.

A baked run has no such table. Both kerbs, their inner edges and the centre
line are all inside the run, so **a one-pixel line is a nibble in a `PUSH`ed
constant** and costs exactly what a six-pixel one costs. The kerbs keep
their red and white all the way to the vanishing point, and the line never
drops out. The only four-pixel floor left is the road itself, whose two
outer edges must land in different `PUSH`es — and it is never narrower than
four pixels anywhere.

The dash rides on the band parity rather than a bit of its own: the line
shows on one band and is the tarmac's own colour on the next. A second bit
would have doubled the bank.

## The stale band puts back two ends, not a row

A row whose band parity has flipped since **this buffer** last had it has
stale grass — but only grass. The window is about to have the road drawn
over it, so what goes back is the screen's left edge to the window's, and
the window's right edge to the screen's: on a wide row that is a handful of
`PUSH`es rather than sixty-four. **2,350 T-states a frame**, and rather
more off the worst frame, which is where it matters.

## The band period is the whole margin

A row whose band parity has flipped since **this buffer** last had it needs
its full width back before the road goes over it. How often that happens is
the band period, and it decided the routine:

| bands | flips | `rd2_frame` then | |
|---|---|---|---|
| 256 world units | one row in six a frame | 121,063 | missed 50 Hz |
| **512 world units** | **one in twelve** | **108,986** | **and the worst frame fit** |

12,077 T-states, and the spread between best and worst frame with it. Those
two numbers are from when the road was narrower and the dispatch three times
dearer; what has not changed is which way the constant goes. The longer
bands also read more like Out Run's, so this one cost nothing at all.

## Invariants

- The integration is **one row ahead of what it draws**: the clamp and the
  centre come out before the depth work, not after. Reverse them and the
  road is a row's worth of `dx` out of place — about a pixel at the far end,
  which is one phase, which is the wrong run.
- The margin must exceed the **two**-frame movement, not the one-frame.
- Rows are drawn **bottom upwards**, because that is the order the bend
  integrates in — and because that is what makes the left hand spill
  repairable: it lands in the row that is drawn next.
- `C` is the band's parity for the whole row: it is the page of both index
  tables and the colour of a fill. The fill uses `DE` for the grass and
  hands `E` back afterwards, because `E` is the run's index.
- The record is 6 bytes and the row loop `POP`s exactly 6. It reads them
  where each is wanted rather than all at once, which is the only reason
  `SP` can be the record pointer and then the screen.
- Nothing in the resident block may carry state from one frame to the next,
  because there is a copy of it behind each buffer and they alternate. The
  exception is each record's parity mark, which is per buffer and wants to
  be. The camera goes in from the caller each frame, which writes whichever
  copy is mapped — the right one, because the flip has already happened.
- `tests/harness_rd2.asm` asserts both blocks — under `0x2000` and clear of
  the stack at the top. The bank grew into the bench's own stack once, and
  what that looks like is a run jumping into the return address.

## What is left

All measured, none applied:

- **Drop the mown stripes** — one grass colour, and a band that moves on
  under a row no longer makes its grass stale, so the repaints go and the
  mark in each record with them. **11,762 T-states** when it was measured,
  against the quantised bank and the whole-row fill, with 9,400 of the
  12,193 spread between best and worst frame; verified bit-exact against a
  model with the same change. It will be worth less now that the fill puts
  back two ends rather than a row, and it is still most of the 13,500 the
  best and worst frame are apart. It is also the whole of what the copper
  was ever going to buy, for nothing.
- **The row loop's memory parks** — ~6,000. Six bytes round-trip through
  memory at 13 T-states each way because nothing is free to hold them; a
  second look at the register allocation should pay for one or two.
- **A margin per row** — ~1,000, and now free in memory too: the margin is
  baked per row already, and the far rows do not need eight pixels of it.

Paired far rows are off the list: they are the staircase again, in the one
place the paged bank has just removed it.

And the thing this still has not got: **a bike**. There are 1,700 T-states
inside 50 Hz at the worst frame as it stands, about 10,000 with the stripes
dropped, and 127,000 if it drops to 25. Memory for its frames is no longer
a question: the bank uses four pages of a machine that has sixteen.

    python3 tests/mkroad2data.py    # regenerate, and self-check the procedure
    python3 tests/test_road2.py     # verify against the model and time
