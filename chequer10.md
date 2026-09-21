# chequer10.z80s — design notes

**Three trees on the board.** chequer9's flight with scenery standing on the
ground: Space Harrier cypresses, compiled at the eight sizes the arcade draws
its scenery at, planted in the world at staggered depths and coming in until
each fills the bottom of the screen. 153,882 T-states a frame on the demo's
own path, 222,452 in its worst frame: **93% of a 25 Hz frame**, of which the
three trees are at most 31,036.

| | T-states a frame | |
|---|---|---|
| **the board** | **28,669 … 124,066** | 19 scanlines (10%) to 96 (50%) |
| **the desert** | **49,866** | 20 scanlines, two layers |
| **the pilot** | **8,056** | 24x48, anywhere on the screen |
| **the trees** | **858 … 31,036** | three slots, 4x13 to 32x135, anywhere on the screen |
| the sky the four left behind | 0 … 12,000 | whatever of their old boxes was above the band |
| the rows the board gave up | 0 … 3,736 | when the horizon drops |
| **`cq10_frame`** | **94,465 / 153,882 / 222,452** | **25 Hz**, 4 frames of 250 over 90% |

**And it runs on a machine.** `build/chequer10.sbt` boots on SimCoupe and
on a 512K SAM: `loader.md` is the note on how the map gets there and what
the demo costs once the ASIC has taken its memory cycles - 1.5 to 2.9
display frames a frame, which is 25 Hz where the board is short and 16.7
where it is tall.

Bit exact against `tests/chequer10.py` over 156 frames: every one of the 78
horizons twice, walked up the screen and back down, with the camera moving,
the pilot in a different place and pose every frame, and three trees at a
different one of the eight sizes each.

## A scaled sprite is eight sprites

Scaling a masked shape as it is drawn costs a Z80 more than drawing it does:
a run of solid bytes is 5.5 T-states a byte through `PUSH`, and any scaler
worth the name is a read, a shift, a merge and a write per byte at four or
five times that — before it has decided which source row a destination row
comes from. So the tree is **compiled eight times**, at the eight heights
the arcade uses, and pops from one to the next as it comes in. That is what
the arcade does too, and at 25 Hz the pop is invisible against the movement.

| rows | box | bytes | masked | drawn | in the frame |
|---|---|---|---|---|---|
| 13 | 2x13 | 24 | 2 | 1,287 | 858 |
| 19 | 2x19 | 34 | 2 | 1,497 | 1,291 |
| 27 | 4x27 | 96 | 12 | 2,672 | 2,243 |
| 39 | 4x39 | 140 | 18 | 3,609 | 3,403 |
| 54 | 6x54 | 260 | 29 | 5,454 | 5,025 |
| 81 | 10x81 | 624 | 76 | 11,119 | 10,913 |
| 105 | 14x105 | 1,060 | 83 | 16,217 | 15,788 |
| 135 | 16x135 | 1,535 | 104 | 22,190 | 24,720 |
| **19 + 54 + 135** | three slots | 1,829 | 135 | **29,141** | **31,036** |

3,773 bytes of *picture* for the lot, which compiles to **10,384 bytes of
code** — a third of the pair of pages the map gives it, and 2.8 bytes of code
a byte drawn. That ratio is the technique's real price: a bitmap and a
general blitter would be the 3,773 and a routine, and would cost several
times the T-states. `drawn` is the whole of `cq10_tree`, which walks all three
slots whether or not they hold anything (384 T-states for the two empty
ones); `in the frame` is what a frame costs with that tree in it rather than
none. They agree except at 135 rows, where the box reaches 19 scanlines above
the band's top and those have to be put back as well.

**It is the pilot's walk, not a second technique.** Each size is one
descending pass of `SP` over its box, exactly as `jetmove.z80s` is:
`PUSH DE` for a run of solid bytes, `POP BC`/mask/`PUSH BC` where a pixel of
sprite meets a pixel of board, and `LD HL,-d / ADD HL,SP / LD SP,HL` to get
from one to the next. `tests/mksprite.py` is that walk, and both generators
call it — which is why the tree cost a day rather than a week.

**And it is never clipped.** A sprite compiled as a walk of `SP` has no idea
where the screen ends: it writes where it is put. So the caller has to know
the whole box fits, and a tree whose box would not is simply not drawn —
which is exactly how a tree leaves in this demo. It grows until the frame it
would no longer fit in, and is gone.

## Three of them, and the depth sort is free

`cq10_tk`, `cq10_tx` and `cq10_ty` are three sizes, three left hand bytes and
three rows to stand on — nine contiguous bytes, because latching them into
this buffer's record is then one `LDIR`. **Slot 0 is the furthest**, and
`cq10_tree` draws them in that order, so a nearer tree paints over a further
one and that is the whole of the depth sorting. The caller keeps the order by
construction: it plants them at staggered depths and sorts three numbers a
frame, which is free in the demo and would be a three-element insertion sort
in a game.

**The page goes in once for all three.** The loop runs with the tree bank
mapped over the low 32K, which is where the caller's stack lives — so nothing
inside it may `PUSH`, `POP` or `CALL`, the slot it is on is a cell rather than
a register, and the box comes out of the *resident* copy of the table. That
copy is at the top of the high 32K, which `HMPR` maps and the `OUT` did not
touch. Each size ends `JP CQ10_RET`, and `cq10_ret` is the top of the loop
rather than the way out: it steps the slot, skips an empty one, and only the
slot past the last restores the bank. The pilot needed his own way back after
that, `cq10_pret`, which is the one line of this that is not obvious.

The Z80 draws what it is told; `tests/chequer10.py`'s `place()` works the
three out from each tree's depth:

    d = z - camz                       how far away it is
    h = TREEH * FOCAL / d              how tall it should be, in pixels
    k = the size nearest that h        one of the eight
    x = W/2 + (x - camx) * FOCAL / d   and where, across the screen

**The row it stands on is the one whose depth matches**, not a row computed
from `d`. A shallow board is the deep one with scanlines left out, so the
depths actually on the screen are a *subset* of the deep board's, and the
tree has to land on one of them. Taking the nearest also keeps it still
relative to the ground while the horizon moves: the same piece of ground,
whichever rows the horizon has chosen to draw.

`TREEH` is 433 world units, which is 1.7 squares — the tree fills the screen
at the depth where the board's squares are 80 pixels wide.

## Putting back what a sprite that moves leaves behind

The band and the board repaint everything below the band's top every frame,
so a sprite standing on the board costs nothing to erase. Above it, the sky
was painted once at init and stays there — so the part of an old box that
was above the band's top has to be put back.

chequer9 did this for the pilot with a fill whose width was assembled in.
Four boxes of three different widths want one routine, so `cq10_wipe` takes
the box in registers and enters **a block of sixteen `PUSH DE` at
`16 - pairs`**
— which is why the tree's widths are rounded to whole pairs of bytes
(2, 2, 4, 4, 6, 10, 14, 16). 38 + 11 T-states a pair per row, so the 135
tree's 19 rows come to 2,904.

**All four boxes are per buffer, and that is still free.** The paged map
keeps a copy of the resident block behind each screen, so `cq10_ox`/`oy` and
the three `cq10_otk`/`otx`/`oty` are each buffer's own record of what it was
last drawn with. `cq10_gone` wipes them and then latches the current
positions —
*whether or not they are drawn*, because a tree that has gone off the bottom
still has to be wiped out of the buffer it was last in.

## The demo's trees

Each planted at a depth of 6,800 — which asks for the smallest sprite of the
eight — and closing at the speed the ground scrolls, 80 world units a frame,
because they are standing still and the camera is not. 77 frames later one
has filled the bottom of the screen and is gone, and another is planted
somewhere else across the playfield. **The three are a third of a life
apart**, which is what keeps the frame affordable: when the near one is at
135 scanlines the other two are at 27 and 19, so three trees cost 31,036
T-states rather than the 66,000 three near ones would. Four frames of the
250 go over 90% of a 25 Hz frame and none over 93%.

Their lateral offsets cycle through six values between ±330 world units, so
no two arrivals land in the same place and the three are never in a line.
Perspective does the rest: at 6,800 units away the whole spread is nine
pixels, which is why the far pair always sit near the middle.

**It is planted beside where the camera *will* be.** The camera pans with the
pilot — ±900 world units as he crosses the screen — and a tree planted
beside where the camera is now is swept off the side of the screen long
before it arrives. Planting it beside the camera's position 77 frames later
keeps it in frame for the whole approach, which is the difference between
scenery you fly past and scenery that never gets close.

## The map

    0,1  2,3  4,5      the board's run bank, the widest bands
    6,7  8,9           the swap mask tables, 512 of them, 96 rows deep
    10,11  12,13       the two buffers, each with the resident code in
                       the 8K a MODE 4 screen leaves at the end of its
                       odd page
    14,15  16,17       the rest of the run bank, up to 80 pixel squares
    18,19  20,21       the desert's rear layer, cut by row
    22,23              the pilot, compiled and position independent
    24,25              the tree, eight sizes of the same

Twenty-six of the thirty-two pages `LMPR` can address, so a 512K SAM — 416K
claimed, 341,130 bytes of it actually holding something:

| | bytes | |
|---|---|---|
| the board's five chunks | 155,320 | compiled row loops, up to 80 pixel squares, and the band lists |
| the swap masks | 65,536 | 512 tables, 96 rows deep, in two chunks that are exactly full |
| the desert's two | 51,834 | the rear layer cut by row, four phases |
| the pilot | 4,032 | three poses |
| the trees | 10,384 | eight sizes |
| the resident block | 4,872 | 2,436 bytes, and there is a copy behind each buffer |
| the two buffers | 49,152 | |

`tests/test_chequer10.py` prints that table every run, chunk by chunk, with
how much of each page pair is used — which is where the 12% on the pilot's
pair and the 32% on the trees' comes from, and the argument for what to put
in the room they leave.

## Invariants

- Everything chequer9's notes list still holds: the band loop's read before
  the `OUT`, the mask gathered before the board, `SP` restored and interrupts
  off wherever `SP` is the screen, a horizon that comes from the table.
- **The order is sky, wipe, mask, board, desert, trees, pilot.** A tree
  stands on the ground, so it goes over the board and the band; the pilot
  flies, so he goes over all three.
- **Slot 0 is the furthest**, and nothing checks it. Hand the slots out of
  order and a far tree paints over a near one.
- `cq10_tree` maps the tree's page over the bank once and enters each size
  with `JP (HL)`; the size ends `JP CQ10_RET`, which is the top of the loop,
  and only the slot past the last puts the bank back. **Nothing inside that
  loop may touch the stack** — the caller's is in the chunk that has just
  been paged away — so the slot is a cell and the boxes come from the
  resident copy of the table.
- The pilot's way back is `cq10_pret`, not `cq10_ret`.
- **The caller guarantees the box is on the screen.** Nothing here clips, and
  a tree whose box would run off the edge writes into the next scanline.
  `place()` returns nothing in that case, and nothing is drawn.
- A sprite's box is a whole number of `PUSH` pairs wide, or `cq10_wipe`
  cannot enter its block at the right offset.

## What is left

- **Three is a budget, not a limit.** `CQ10_TREES` is an `EQU` and the loop
  does not care; what costs is the near end, because one tree at 135
  scanlines is 22,190 T-states and the whole frame has about 30,000 spare at
  the tallest board. Six trees spread over the same depth range would fit;
  six near ones would not.
- **Nothing here is specific to trees.** A slot is three bytes and a table of
  boxes; a second kind of object is a second `TREE_BANK`, or the same page
  with a size index that runs past the trees.
- **Nothing is clipped.** Scenery that leaves at the side of the screen
  rather than the bottom needs either a clipped variant of each size (eight
  more sprites) or a column-wise entry into the walk, which is the same
  trick `cq10_wipe` uses for its widths.
- **21,806 T-states for the biggest tree** is 5.5 T-states a byte plus the
  masked edges, which is the floor for this technique. What would beat it is
  not drawing the sky behind it: the tree's box is 29% air at the
  largest size, and every byte of it is written twice.
- The frame is still bus-bound rather than instruction-bound — 57,994 memory
  cycles at the tallest board with three trees on it, one every **3.77
  T-states** against a `PUSH` fill's floor of 3.67, and 18,760 of them bytes
  onto the screen. See `costs.md` §1b. The tree barely moves that ratio,
  which is the point: they are writes with almost no arithmetic between
  them.

    python3 tests/mkchq10data.py              # the board, the desert, the pilot, the tree
    python3 tests/tree.py /tmp/trees.png      # look at the eight sizes
    python3 tests/test_chequer10.py           # verify against the model
