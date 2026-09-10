# balls.z80s — design notes

Vector balls: twenty of them at a cube's corners and edge midpoints, turning
together. **108,270 T-states a frame, 55.4 Hz**, verified byte-for-byte
against `tests/balls.py` over 256 frames.

## The one idea

**Every coordinate is −S, 0 or +S**, because the balls sit on a cube's eight
corners and twelve edge midpoints. A rotated coordinate is
`m0·x + m1·y + m2·z`, so if x, y and z can only be those three values then
the nine products `(m[j]·S)>>7` are worked out **once a frame** and a ball's
position is three signed adds.

Nine multiplies a frame instead of nine a ball. No multiply tables, no
`transform3d` — `balls.z80s` needs `mul8x8_qs` and `democube`'s spin, and
that is all.

The nine are stored **transposed**, `ms[k][j]` rather than `ms[j][k]`, so
the three things one coordinate contributes are next to each other and the
inner loop walks them with `INC HL`.

The projection is `transform3d`'s: `64/z` from a reciprocal table and two
8×8 multiplies a ball. The balls are drawn back to front as rows of whole
bytes, so nothing needs a mask, and each one remembers where it was in each
buffer and blanks that — `stars.z80s`'s trick, and for the same reason: a
full screen erase is 135,000 T-states.

## What it costs

| | T-states | |
|---|---|---|
| `bl_pos` | ~25,000 | 20 balls: three adds, a reciprocal and two multiplies each |
| `bl_draw` | ~29,800 | |
| `bl_erase` | ~23,200 | |
| `bl_sort` | ~19,200 | twenty by insertion, farthest first |
| `demo_spin` | 6,546 | one matrix for all of them |
| `bl_ms` | 2,995 | the nine products |
| **`bl_frame`** | **min 86,035, mean 108,270, max 123,483** | 55.4 Hz mean |

**The worst frame is 3,483 T-states over the 50 Hz budget** — 48.6 Hz — so
a busy pose drops one. The mean has 12,000 to spare.

Three things took it there from 127,378:

1. **The sort was recomputing an address per comparison.** `bl_zof`
   multiplied the ball index by three and pushed a register to reach its z.
   A flat `bl_z` array of one byte a ball made a comparison a lookup:
   24,836 → 19,171.
2. **The blit wrote a byte a pass** at 27 T-states each — a store, an
   increment, a decrement and a branch. Every row of a ball is an even
   number of bytes, so two a pass halves the counter's share.
3. **`bl_pos` called a subroutine nine times a ball** to add one product.
   Inlined, and with the products transposed so one coordinate's three are
   adjacent, it went 31,769 → ~25,000.

## If you pick this up

1. **The sort is 18% of the frame for twenty items.** It is an insertion
   sort because the order barely changes between frames, which is its best
   case — but the comparison still walks memory. A rank built from the
   previous frame's order would be cheaper.
2. **Erase and draw are half the frame** for 40 blits of 20 bytes. The
   shape is data (`bl_rows`), so it cannot be unrolled without pinning it;
   pinning it would be worth about 400 T-states a blit.
3. **Balls do not scale with distance.** Two or three sizes chosen by z
   would cost a table of sprites and a branch, and would sell the
   perspective much better than the four shades do.

## Invariants

- Coordinates must stay in {−S, 0, +S}: the whole cost model depends on it.
- `S` and `TZ` are pinned by the reciprocal table's floor — `TZ − S` may not
  go below `BL_ZMIN`, or a near ball's `64/z` will not fit in a byte.
- Every row of the ball must be an even number of bytes, because the blit
  writes two at a time.
- The sort must be **stable and descending**, matching the model's, or two
  balls at the same distance swap and the overlap changes.

    python3 tests/mkballsdata.py    # the formation, the ball and the tables
    python3 tests/test_balls.py     # verify against the model, and time
