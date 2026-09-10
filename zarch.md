# zarch.z80s — design notes

**Zarch's ground: a chequered plane under a camera that turns.** 208,206
T-states a frame — **87% of a 25 Hz frame**, worst case 90% — verified byte
for byte against `tests/zarch.py` over 96 cameras: every yaw in the table,
at four camera positions each.

| | T-states |
|---|---|
| the screen itself, 56 rows × 128 bytes at 5.5 | 39,424 |
| `za_setup`, both families | 11,512 |
| the row loop, 56 × ~700 | ~39,000 |
| the spans, ~700 of them at ~110 to work out and 33 to draw | ~118,000 |
| **`za_frame`** | **min 195,482, mean 208,206, max 215,619** |

## The one idea

A camera that does not roll means **a screen row is one depth**. So the
ground line a row looks along is straight and level, and a family of
parallel grid lines crosses it at even intervals — which project to even
intervals *on the row*, because at one depth the projection is linear.

So on every row, each of the two families is an **arithmetic progression**:
a position and a step, both of which walk down the screen by adding a
constant. Nothing is projected per vertex, no edge is walked, nothing is
sorted. And because the chequer flips at every crossing of *either* family,
the merge of the two progressions does not even have to remember which
family a crossing came from — it is one comparison and one subtraction a
span.

That is the whole renderer. A row is:

    while the larger of the two positions is above zero:
        emit the span from there to the last boundary
        subtract that family's step from it

## Everything is 8.8 fixed point in PUSHes

A `PUSH` is two bytes, which is four pixels, so positions count in PUSHes
rather than pixels. Two things fall out of that:

- **The high byte of a position is the span boundary**, with no shifting at
  all: `LD E,A` and the merge has its answer.
- **A step stays inside 16 bits** even when a family is nearly edge on and
  its lines are a thousand pixels apart, which is what lets the camera turn
  through the whole of the table rather than a narrow window.

The cost is that a boundary lands on a four pixel grid, which is
`chequer.z80s`'s grain rather than `chequer3.z80s`'s. Pixel-exact edges
want a mixed pair at each boundary — chequer3's trick — and about 20
T-states a span, which this cannot afford at 700 of them.

## The span dispatch is 33 T-states

`spanfill.z80s` measured a span at 63. Half of that goes if the two runs of
`PUSH`es and the row's list of spans all live in **one page**:

    za_f0:  LD   L,A            ; A is the offset into the list
            DEC  A              ; and survives a run untouched, because
            DEC  A              ; a run is nothing but PUSHes
            LD   L,(HL)         ; H never changes: the entry, straight
            JP   (HL)           ; into the low half of the jump

`LD L,(HL)` is the whole trick. The second colour is the same list entry
with bit 7 set — `SET 7,L` in the other loop — so the entry byte does not
carry a colour at all, and the runs' exits jump to the *other* loop, which
is how the chequer alternates for nothing. A span of n PUSHes is entered at
64 - n, and a span of none lands on the `JP` at 64, which is exactly right.
**The list's last entry points at a `JP` out of the row, so the loop has no
test in it.**

## Where the awkwardness is

**A position is signed.** A family whose lines are further apart than the
screen is wide has none of them on a row at all, and then the rightmost is
off to the left and negative. The row loop's tests are `SUB 0x40 / CP 0x40`,
true only for a high byte between 0x40 and 0x7F — at or past the right hand
edge, and not negative — and the walk parks such a family at the left edge,
where it can never win a comparison.

**Lines come on from the right as well as going off it.** When a family's
lines radiate from a point beyond the right hand edge, they all walk left as
the rows go down, and one steps on from beyond the edge every so often. Both
directions flip which colour is out there.

**`za_setup` counts rather than steps.** Walking out to the right hand edge
is a dozen adds, and each one changes the rightmost line's step down the
screen and the colour beyond it. Doing that work inside the loop cost 300
T-states an iteration through `IX`; counting the lines walked over and
working out `d0 + k alphas` once at the end costs 40.

**The row loop CALLs.** The last thing `SP` did was walk the screen, so the
row loop puts it back before anything calls anything.

## What it is not

**It is flat.** Zarch's landscape has hills, and hills cost what
`demo-ideas.md` §15 says they cost: every vertex projected rather than every
line end, two edges a quad rather than one progression a family, and
overdraw. That is a `vox`-class routine at 13-17 Hz, not this.

**The ground is 56 rows.** The rows near the horizon are where the cells
compress and the span count runs away — 21 spans in a row at the top against
5 at the bottom — so the board stops there and a haze meets the sky, exactly
as `harrier.z80s` does it. Four more rows cost about 11,000 T-states.

## Invariants

- `SP` walks the screen and then the list, so interrupts are off and
  `za_sp` holds the caller's stack.
- The spacing widens *before* the rightmost line steps down: the tests
  want the new one.
- The two runs and the list must stay in one page, and the list is built
  downwards from the top of it by `PUSH AF`, two bytes a span of which one
  is the flags and ignored.
- The camera's own cell is a parity like any other: cross one and the two
  colours change places, which is `chequer`'s bug over again.

    python3 tests/mkzadata.py       # regenerate the yaw and shade tables
    python3 tests/test_zarch.py     # verify against the model and time
