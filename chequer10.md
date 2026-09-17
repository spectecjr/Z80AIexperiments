# chequer10.z80s — design notes

**A tree on the board.** chequer9's flight with one piece of scenery standing
on the ground: a Space Harrier cypress, compiled at the eight sizes the
arcade draws its scenery at, planted in the world and coming in until it
fills the bottom of the screen. 144,254 T-states a frame on the demo's own
path, 210,517 in its worst frame: **88% of a 25 Hz frame**, and the tree is
at most 24,710 of it.

| | T-states a frame | |
|---|---|---|
| **the board** | **28,669 … 124,066** | 19 scanlines (10%) to 96 (50%) |
| **the desert** | **49,866** | 20 scanlines, two layers |
| **the pilot** | **8,056** | 24x48, anywhere on the screen |
| **the tree** | **903 … 21,806** | 4x13 to 32x135, anywhere on the screen |
| the sky the two left behind | 0 … 8,000 | whatever of their old boxes was above the band |
| the rows the board gave up | 0 … 3,736 | when the horizon drops |
| **`cq10_frame`** | **88,358 / 144,254 / 210,517** | **25 Hz** |

Bit exact against `tests/chequer10.py` over 156 frames: every one of the 78
horizons twice, walked up the screen and back down, with the camera moving,
the pilot in a different place and pose every frame, and a tree at a
different one of its eight sizes.

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
| 13 | 2x13 | 24 | 2 | 903 | 848 |
| 19 | 2x19 | 34 | 2 | 1,113 | 1,281 |
| 27 | 4x27 | 96 | 12 | 2,288 | 2,233 |
| 39 | 4x39 | 140 | 18 | 3,225 | 3,393 |
| 54 | 6x54 | 260 | 29 | 5,070 | 5,015 |
| 81 | 10x81 | 624 | 76 | 10,735 | 10,903 |
| 105 | 14x105 | 1,060 | 83 | 15,833 | 15,778 |
| 135 | 16x135 | 1,535 | 104 | 21,806 | 24,710 |

3,773 bytes of sprite for the lot — a quarter of one 16K page, and the
map gives it two. The last column is what a frame costs with that tree in it
rather than none — the same number, except at 135 rows, where the box
reaches 19 scanlines above the band's top and those have to be put back as
well.

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

## Where it stands is arithmetic, and it is the model's

`cq10_tk`, `cq10_tx` and `cq10_ty` are the size, the left hand byte and the
row it stands on. The Z80 draws what it is told; `tests/chequer10.py`'s
`place()` works them out from the tree's depth:

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
Two sprites of different widths want one routine, so `cq10_wipe` takes the
box in registers and enters **a block of sixteen `PUSH DE` at `16 - pairs`**
— which is why the tree's widths are rounded to whole pairs of bytes
(2, 2, 4, 4, 6, 10, 14, 16). 38 + 11 T-states a pair per row, so the 135
tree's 19 rows come to 2,904.

**Both boxes are per buffer, and that is still free.** The paged map keeps a
copy of the resident block behind each screen, so `cq10_ox`/`oy` and
`cq10_otk`/`otx`/`oty` are each buffer's own record of what it was last drawn
with. `cq10_gone` wipes both and then latches the current positions —
*whether or not they are drawn*, because a tree that has gone off the bottom
still has to be wiped out of the buffer it was last in.

## The demo's tree

Planted at a depth of 6,800 — which asks for the smallest sprite of the
eight — and closing at the speed the ground scrolls, 80 world units a frame,
because it is standing still and the camera is not. 77 frames later it has
filled the bottom of the screen and is gone, and the next one is planted on
the other side of the flight path.

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

Twenty-six of the thirty-two pages `LMPR` can address, so a 512K SAM.

## Invariants

- Everything chequer9's notes list still holds: the band loop's read before
  the `OUT`, the mask gathered before the board, `SP` restored and interrupts
  off wherever `SP` is the screen, a horizon that comes from the table.
- **The order is sky, wipe, mask, board, desert, tree, pilot.** The tree
  stands on the ground, so it goes over the board and the band; the pilot
  flies, so he goes over the tree.
- `cq10_tree` maps the tree's page over the bank and enters with `JP (HL)`,
  and the size ends `JP CQ10_RET`, which puts the bank back. The box is read
  from the *resident* copy of the table before the page is mapped, because
  `SP` has to be on the corner first.
- **The caller guarantees the box is on the screen.** Nothing here clips, and
  a tree whose box would run off the edge writes into the next scanline.
  `place()` returns nothing in that case, and nothing is drawn.
- A sprite's box is a whole number of `PUSH` pairs wide, or `cq10_wipe`
  cannot enter its block at the right offset.

## What is left

- **The tree is the only thing on the board.** Nothing here is specific to
  one: `cq10_tk`/`tx`/`ty` are a sprite slot, and a second slot is another
  three cells and another `CALL`. Four small trees at 2,000 T-states each
  cost what one near one does.
- **Depth order is the caller's problem** the moment there are two. They
  would have to be drawn far to near, which is a sort of up to as many
  objects as there are slots — cheap at four, and a reason not to go to
  forty.
- **Nothing is clipped.** Scenery that leaves at the side of the screen
  rather than the bottom needs either a clipped variant of each size (eight
  more sprites) or a column-wise entry into the walk, which is the same
  trick `cq10_wipe` uses for its widths.
- **21,806 T-states for the biggest tree** is 5.5 T-states a byte plus the
  masked edges, which is the floor for this technique. What would beat it is
  not drawing the sky behind it: the tree's box is 29% air at the
  largest size, and every byte of it is written twice.
- The frame is still bus-bound rather than instruction-bound — 56,088 memory
  cycles at the tallest board with the biggest tree on it, one every **3.76
  T-states** against a `PUSH` fill's floor of 3.67, and 18,416 of them bytes
  onto the screen. See `costs.md` §1b. The tree barely moves that ratio,
  which is the point: it is writes with almost no arithmetic between them.

    python3 tests/mkchq10data.py              # the board, the desert, the pilot, the tree
    python3 tests/tree.py /tmp/trees.png      # look at the eight sizes
    python3 tests/test_chequer10.py           # verify against the model
