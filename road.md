# road.z80s — design notes

**A Hang On road: it steers, and it bends as you ride along it.**
172,141 T-states a frame — **72% of a 25 Hz frame**, and near enough the
same number whatever the camera is doing.

Verified bit-exact against `tests/road.py`, pixels and parities, over 90
camera positions.

| | T-states |
|---|---|
| the 6,080 `PUSH`es — 95 rows of 128 bytes | 66,880 |
| the rest: 378 span dispatches and 95 rows of geometry | ~105,000 |
| **`rd_frame`** | **min 171,906, mean 172,141, max 173,236** |
| `rd_init` | 1,428,973 once |

## The one idea is still the palette's

`chequer.md` is the file to read first: with the camera height fixed, one
scanline is one depth, so **anything constant along a scanline belongs to
the palette rather than the pixels**. On a chequerboard that buys the depth
stripes. On a road it buys rather more, because almost everything a road has
is constant along a scanline:

- the mown stripes in the grass,
- the light and dark bands in the tarmac,
- the red and white of the kerbs,
- and the dashes down the middle.

All four come out of **two bits a scanline** — bits 6 and 7 of that row's
depth, one 16-bit add to work out — and the whole screen is drawn in four
colour indices whose meaning is set per scanline. So **riding forward costs
nothing in pixels at all**, exactly as it does on the chequered floor, and
the fade into the horizon comes free on top. Only steering and the bend move
a pixel.

The centre line is the nicest of the four: it is drawn as a span on every
row that is wide enough for one, and the *dashes* are the palette turning
index 4 from white to the tarmac's own colour and back as the depth crosses
each 128 units. A dashed line that costs the same as a solid one.

## The bend

The arcade's, and it is two adds a row:

    dx += curvature at this row's depth
    x  += dx

`x` is the road's centre in 8.8 pixels and the curvature comes from a
64-segment track, indexed by bits 9 to 14 of the same depth the parities
came from — so the track scrolls past underneath as `camz` grows and a bend
sweeps down the screen towards you.

**Steering needs no multiply either.** A lateral offset of *camx* world
units projects to `camx * (y - HZ) / CAMH` pixels, which is linear in the
row, so it is not a per-row multiply but *the constant of the first
integration*: start `dx` at `camx` and the ramp comes out of the same two
adds as the bend. `CAMH` is 256 precisely so that a world unit of `camx` is
one 8.8 pixel of step. The only multiply in the routine is the one that puts
`x` at the bottom of the screen, `0x8000 - 95 * camx`, once a frame.

That the camera's own offset is the integration constant is the whole reason
this is cheap, and it is worth saying plainly: `chq_entry` needed a table and
an add a period to scale one offset down the screen, and this needs neither.

## Nothing is ever clipped

A boundary off the side of the screen would want a `PUSH` that does not
exist, and the arithmetic that works out how many `PUSH`es to do would have
to test for it — six times a row. So instead the centre is **held inside
`[w, 255-w]`**, which is one compare against each rail a row, and the road
always fits.

That is not the restriction it looks like. The road is **126 pixels wide at
the bottom of a 256 pixel screen for exactly this reason**: `RW` is 170
world units and 170 world units of `camx` is 63 pixels of shift at the
bottom row, which is one half-width. **The camera can sit over either kerb
and still see the whole road**, and it can only want clipping by leaving the
road altogether — at which point the road stops at the edge of the screen
rather than sliding off it.

Two consequences, both good:

- **No span is ever empty**, so there is no test for one anywhere in the
  chain: a span is `LD A,(boundary)`, four instructions of arithmetic and a
  `JP (HL)`.
- The cost is **the same every frame to within 1,300 T-states**, all of
  which is the rails being hit. A routine whose worst case is its average
  is a routine you can budget a bike sprite against.

The rails stop four pixels short of the screen's own edges where the road is
narrower than that, which is what keeps the 8.8 accumulator clear of its own
wrap: `dx` can reach 656.

## Three bands, not six tests

A kerb narrower than four pixels would put two boundaries inside one `PUSH`,
which carries a pixel of each colour and so can hold only one; the same goes
for the centre line. **Which rows those are is fixed by the row**, not by
the camera, so rather than test, the screen comes in three bands:

| rows | | spans |
|---|---|---|
| 157–191 | kerbs and a centre line | 7 |
| 133–156 | kerbs | 5 |
| 97–132 | the road is too narrow for either | 3 |

and the chain is **patched twice a frame**. A span's dispatch begins with
`LD A,(nn)`, which is three bytes, and so is `JP nn` — so patching one
opcode turns a span into a jump over it, and the band with no kerbs goes
from the first span straight to the last. The last one's colour and its
boundary's pair of colours are patched with it, because on that band the
road meets the grass directly.

## A span

    LD   A,(rd_e5)      ; the boundary, in pixels
    RRCA
    RRCA
    AND  63             ; which PUSH it falls in
    LD   L,A
    SUB  D              ; and how far that is from the last one
    ADD  A,65
    LD   D,L
    LD   BC,RD_GRASS
    LD   H,rd_p0 / 256
    LD   L,A
    JP   (HL)

72 T-states to enter a run of 64 `PUSH BC` as many from its end as the span
is wide, and 71 more at the bottom of the run for the `PUSH` that straddles
the boundary — `harrier`'s mixed pair, one of eight pairs of colours here
rather than one of two. 143 T-states a span, of which 11 is a `PUSH` the row
had to do anyway, so 378 spans are 54,054 of the frame and the 95 rows of
geometry are the other 51,000.

The run pages hold the *next* span's dispatch after the boundary `PUSH`, so
the chain falls through page to page with no jumps in it: seven pages, and
the last one runs out into the row loop.

## Invariants

- The centre is **pinned** to the rails, not merely reported as outside
  them: the accumulator is written back clamped, or the road creeps away
  and comes back through the other edge.
- Rows are drawn **bottom upwards**, because that is the order the bend
  integrates in — the shape is curvature accumulated outwards from where
  the camera is standing, so the near row has to be worked out first.
- `BC` is the colour being pushed and `D` is the `PUSH` the last boundary
  fell in, for the whole of a row: the row pointer, its step and the band's
  row count live in the other register set, `IX` is the centre and `IY` the
  row's record.
- Every span is at least four pixels wide, or two boundaries land in one
  `PUSH` and the narrower one is drawn a pixel or three too wide.
  `MINSPAN` in `tests/road.py` is where that is enforced, and it is why
  the kerbs and the centre line stop where they do.
- The track's curvature is small on purpose. Integrated twice up 95 rows, a
  peak of 7 is about a hundred pixels of swing at the horizon, and much more
  than that and the far end of the road sits on the rail.

## What is not verified

Same as `chequer.z80s`, and for the same reason: the frame writes two
parities a scanline and every bit of that is checked against the model, but
what the display does with them — **four** CLUT writes in the line interrupt
rather than chequer's two — is not, because the test bench is a plain Z80
with no SAM ASIC in it. `rd_out` is the loop that would run.
`tests/mkgif.py` applies the parities and `rd_fog` when it writes the GIF,
so `demo/road.gif` shows what the screen would show.

## If you pick this up

**A bike, and then a game.** There are 68,000 T-states left in a 25 Hz
frame, and `chequer6`'s pilot cost 25,528 for 32×96 pixels of person. The
road already hands a sprite everything it needs to sit on it: `rd_e0` to
`rd_e5` are where the road's edges are, on the row you want them.

**Fifty hertz wants the compiled runs.** The 105,000 T-states that are not
`PUSH` are the price of working out, six times a row, how many `PUSH`es to
do. `chequer3` shows the way out: the *shape* of a row — kerb, tarmac, line,
tarmac, kerb — depends only on the row, and only its *position* moves, so a
row could be one compiled run positioned by `SP` rather than six dispatches.
That is `chequer3`'s trick with the sides of the road in place of the phase,
and it would take the span dispatches to one a row. The awkward part is the
same as it is here: what a compiled run cannot do is clip, and this file
buys its way out of clipping with a narrow road.

**Hills.** The road's rows are at fixed depths because the camera height is
fixed, which is what makes one scanline one depth and the whole palette
trick work. A crest or a dip breaks that — and `vox.z80s` is what it costs
when it breaks.

    python3 tests/mkroaddata.py     # regenerate the tables
    python3 tests/test_road.py      # verify and time
