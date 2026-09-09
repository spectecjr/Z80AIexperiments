# roto.z80s — design notes

A rotating, zooming texture. This is the expensive case, and it exists to
measure it: **109.7 T-states for an arbitrary computed byte**, which is the
number the rest of this repo was missing.

Verified bit-exact against `tests/roto.py` over 12 angles and zooms.

## Why it is dear

Every byte of the picture is a different texel, so there is no run structure
to exploit at all — no `PUSH` run can be entered n from the end, nothing is
constant along anything. Against the rest of the repo:

| | T-states a byte |
|---|---|
| constant run along a row, `PUSH` | 5.5 |
| textured wall column, four pixels wide | 14.5 |
| flat column | 18.4 |
| textured wall column, two pixels wide | 22.8 |
| **arbitrary computed byte** | **109.7** |

That is why the window is 128×64 pixels and not the screen: 4,096 bytes at
109.7 is 449,272 T-states, which is 13.4 Hz. The whole screen would be 2.7
million — about 2 Hz.

## The inner loop

The texture is 16×16 and page-aligned, so a texel's address is **one byte**:
the row in the top nibble, the column in the bottom. The two accumulators
and their steps do not fit in one register set, so:

    alternate   HL = u, DE = v, BC = du, SP = dv
    main        HL = texture page and address, DE = where the byte goes,
                B  = how many are left

`SP` holds `dv` because `ADD HL,SP` is the only other sixteen-bit add there
is — which is also why the output is `LD (DE),A` rather than `PUSH`: `PUSH`
wants `SP`, and `SP` is spoken for. Only `A` survives `EXX`, so the address
byte has to be finished — both nibbles, OR'd — before coming back.

## The one subtlety

**u is 8.8 and v is 4.12.** Masking u's high byte to four bits every step is
harmless: it keeps u modulo 4096 and leaves the fraction in L alone. v is
scaled so its row is already in the top nibble of its high byte, and it
wraps of its own accord in sixteen bits — so masking *that* one back would
eat four bits of its fraction and the texture would drift. Extract, do not
write back. (This was a bug, and it drifts slowly enough to look plausible.)

The driver must scale to match: `du`/`dux` in 8.8, `dv`/`dvx` in 4.12 — a
factor of sixteen between them.

The inner loop steps *before* it samples, so the model does too.

## If you pick this up

The 109.7 breaks down as roughly 30 for the two sixteen-bit adds, 22 for the
two masks and the OR, 16 for the two `EXX` and two `EX DE,HL`, 14 for the
fetch and the store, and 13 for the loop. The shuffling is the only part
that looks like waste, and it is there because a Z80 has one spare
sixteen-bit add and two spare pairs.

A 4K texture (16 rows × 256 columns) would remove u's mask, but then the
address is two bytes and only `A` crosses `EXX` — so it does not pay. What
might: unrolling the loop and alternating which register pair holds what, so
some of the `EX DE,HL` disappears.

    python3 tests/mkrotodata.py     # regenerate the texture
    python3 tests/test_roto.py      # verify and time
