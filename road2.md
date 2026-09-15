# road2.z80s — design notes

**The same road as `road.z80s`, with the palette nailed down, at 50 Hz.**
108,986 T-states a frame — **91% of a 50 Hz frame, worst frame included** —
against `road.z80s`'s 172,141 at 25 Hz.

Bit-exact against `tests/road2.py` over 198 frames of a ride. Not a list of
poses: a frame here depends on the two before it, so the test drives a whole
ride and checks every frame of it against the *ideal* picture — which the
routine has to land on however little of it it chose to touch.

| | T-states a frame |
|---|---|
| the compiled runs — the road itself | 21,625 |
| dispatch and the row loop | 15,390 |
| grass | 4,180 |
| the bands moving on | 0 to 9,000 |
| the geometry, 95 rows | the rest, ~63,000 |
| **`rd2_frame`** | **min 105,020, mean 108,986, max 114,000** |
| `rd2_init` | 1,294,796 once |

(The first three are derived from the counts, not measured separately; only
the totals are measurements.)

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
grass is worth 14,300 at most. Break-even needs 63% of rows flipping band
per frame, which is a speed at which the bands have already aliased into
mush.

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

That is about **twenty `PUSH`es a row rather than sixty-four**, and it needs
no record of where the road was — which is the part worth keeping. Because
the window moves *with* the road, the geometry of a row relative to its own
window never changes: **every entry in the tables is a constant**, and the
only runtime value a whole row needs is where to put `SP`.

**The margin is not slack, it is a speed limit.** It has to cover what the
road moves in the *two* frames a buffer waits its turn — 8 pixels at 20
world units a frame, which is exactly `M`. At 30 it wants 11, at 40 it wants
14. Get this wrong and the road leaves a trail.

## One compiled run a row

A row's road has a shape fixed by the row — the kerbs are `w/6`, the centre
line `w/10` — and only its *position* moves. So it compiles once and `SP`
places it: `chequer3`'s trick with the road's edges in place of the phase.

A row is then **three dispatches**: grass in from the right, the run, grass
out to the left. The run is one byte a `PUSH` where the colour holds and
four where it changes, which is at six places and nowhere else, so a wide
road is mostly `PUSH HL` at 11 T-states.

The bank is indexed by (half width, phase, band parity). 62 widths cover 95
rows because consecutive rows share one; **phase is one pixel**, because
`SP` is a byte address and places the road to two pixels on its own; parity
doubles it, because the solid colours could come from registers but the
baked boundary bytes could not. 248 runs, 9,367 bytes, split across the two
blocks either side of the screen buffers the way `chequer3`'s bank is.

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

## The band period is the whole margin

A row whose band parity has flipped since **this buffer** last had it needs
its full width back before the road goes over it. How often that happens is
the band period, and it decided the routine:

| bands | flips | `rd2_frame` | |
|---|---|---|---|
| 256 world units | one row in six a frame | 121,063 | misses 50 Hz |
| **512 world units** | **one in twelve** | **108,986** | **and the worst frame fits** |

12,077 T-states, and the spread between best and worst frame with it. The
longer bands also read more like Out Run's, so this one cost nothing at all.

## Invariants

- The integration is **one row ahead of what it draws**: the clamp and the
  centre come out before the depth work, not after. Reverse them and the
  road is a row's worth of `dx` out of place — about a pixel at the far end,
  which is one phase, which is the wrong run.
- The margin must exceed the **two**-frame movement, not the one-frame.
- `A` carries the left hand grass entry through the whole run — nothing
  between `rd2_road` and `rd2_out` may touch it, and the compiled runs
  use only `HL`.
- `BC` is the grass pair for the whole row, both ends of it.
- Rows are drawn bottom upwards, because that is the order the bend
  integrates in.
- The record is 14 bytes and the row loop `POP`s exactly 14. It reads them
  where each is wanted rather than all at once, which is the only reason
  `SP` can be the record pointer and then the screen.

## What is left

**The geometry is now the routine.** ~63,000 of 109,000, and none of it is
`PUSH`: it is the record, the clamp, the curvature lookup, the two
integrations and the phase, 95 times. The drawing that used to be the whole
problem is 46,000.

Measured or costed, and none of them needed yet:

- **Drop the grass stripes** — ~5,500, and more usefully the entire 9,000
  spread between best and worst frame. The cost is flat after it.
- **A margin per row** — ~2,000, and free: the far rows move 8 pixels and
  the near ones barely move, and the margin is baked per row already.
- **The geometry's register parks** — ~3,000. Six values round-trip through
  memory at 13 T-states each way.
- **Paired far rows** — ~8,000, at the cost of two-row stairs on the far
  road edges.

And the thing this still has not got: **a bike**. There are 11,000 T-states
inside 50 Hz for one, or 131,000 if it drops to 25.

    python3 tests/mkroad2data.py    # regenerate, and self-check the procedure
    python3 tests/test_road2.py     # verify against the model and time
