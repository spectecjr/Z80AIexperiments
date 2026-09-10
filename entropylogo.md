# entropylogo — the artwork, traced

The Entropy logo as nine convex quads, taken from `entropylogo.png` rather
than from a description. `PRISM_SHAPE=entropy` builds it; without that both
prisms build the provisional shape, which is seven pieces and cheaper.

**220,823 T-states a frame, 27.2 Hz** precomputed (`entropypre`), and
550,669, 10.9 Hz worked out live (`prism`). Both verified byte-for-byte
against `tests/prism.py`, and the precomputed one against the live one as
well, 0 mismatches.

## Tracing it

The artwork is 138×99 with three flat colours and antialiasing on the
diagonals. `tests/entropylogo.py` holds the result; the method was:

1. Classify every pixel white, red or black.
2. Boundary-trace each colour's largest region with a Moore neighbourhood,
   and trace the enclosed holes separately.
3. Simplify with Douglas-Peucker at 1.6 pixels. That gave the sigma twelve
   vertices and the triangle three, plus three for its hole.
4. Move the origin to the middle of the artwork, at (70, 48), and turn y
   the right way up.

**It scores itself.** `python3 tests/entropylogo.py` rasterises the vectors
back at the artwork's own 138×99 and diffs them: **405 of 13,662 pixels
differ, 3.0%**, and all of it is the antialiasing. That number is printed
every time the file is run, so a re-trace from better artwork can be
compared against this one directly.

Three things the pixels settled that a description had not:

- **The sigma's bars are cut back to points.** A single straight edge runs
  from the top-right corner down-left to (43, 23), which is what makes the
  black notch between a bar and its arm.
- **The sigma's left edge is notched**, a chevron with its point at (−1, 0).
- **The triangle is solid with a small triangular hole**, low and left, not
  a thin ring.

## The pieces

Six for the sigma — a bar and its tapered end and an arm, twice — and three
for the triangle's ring, which is the least an annulus can be cut into.
`tests/entropylogo.py` checks what prism's pipeline needs:

- every piece convex and wound clockwise with y up;
- no two pieces overlapping, only abutting;
- **every pair separated by one of their own side faces**, which is what
  `pr_order`'s planes are built from.

Fourteen of the 54 faces are buried in the joins and never drawn — `buried()`
finds them from the geometry.

## What nine pieces cost

| | provisional | entropy |
|---|---|---|
| pieces | 7 | 9 |
| faces | 42 | 54 |
| buried faces | 10 | 14 |
| distinct normals | 18 | 21 |
| ordering pairs, growing as n² | 21 | 36 |
| prismpre's table a frame | 144 bytes | 184 |
| `prism` | 461,171 | 550,669 |
| `prismpre` | 205,008 | **220,823** |

**prismpre pays only 8%** because most of its frame is the fill and the new
pieces are small. prism pays 19%: `pr_proj` is per piece and `pr_order` per
pair.

## The two things nine pieces broke

**`pr_order`'s sets were bytes.** A bit a piece in a byte is eight pieces,
and the ninth needs sixteen — so `pr_fr`, `pr_ov` and `pr_left` are words,
`pr_bit` is a word a piece, and the popcount table is 256 entries rather
than 128. That costs the seven-piece shape 14,569 T-states a frame
(446,602 → 461,171) and costs prismpre nothing, its order being a table.

**The points stopped fitting in one place.** 184 bytes a frame over 64
frames is 11,776, and there are 7,680 above the screen buffers. So a
frame's points are found through a table of pointers: 53 frames of them
live high and eleven down in the low 8K beside the records. The record
stride, which used to be a hard-coded chain of shifts, is multiplied out,
so prismpre no longer cares how many pieces a logo has.

That still only fits because **the quarter-square multiply goes**: prismpre
never multiplies anything, and renderlit only names `qsmul8` from paths it
never calls, so the entropy harness stubs it and gets 1,280 bytes back.

## If the artwork improves

The shape is three lists in `tests/entropylogo.py` — `SIGMA_TOP` (the top
half; the bottom is mirrored), `TRI_OUT` and `TRI_IN`. Re-trace, drop the
numbers in, and regenerate:

    PRISM_SHAPE=entropy python3 tests/mkprismdata.py
    PRISM_SHAPE=entropy python3 tests/mkprismpredata.py
    PRISM_SHAPE=entropy python3 tests/test_prism.py
    PRISM_SHAPE=entropy python3 tests/test_prismpre.py

Worth knowing before that pass: **the hole costs two pieces** — three for
the ring against one for a solid triangle — and at the size the logo is
drawn it is about four pixels across.
