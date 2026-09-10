# chequer5 — design notes

**The same routine as `chequer4.z80s`, byte for byte, with the board drawn
all the way to the horizon.** Squares down to a single pixel wide, no haze
at all: 95 scanlines of board where chequer4 draws 84. There is no
`chequer5.z80s` — only a viewport, a run bank and a set of tables, which is
the point.

| | scanlines | narrowest square | T-states a frame | |
|---|---|---|---|---|
| `chequer4` | 84 | 8 px | 110,835 / **114,656** / 118,586 | 50 Hz |
| **`chequer5`** | **95** | **1 px** | 125,343 / **129,183** / 133,151 | **25 Hz** |
| `harrier` | 84 | 8 px | 220,394 / **221,451** / 223,413 | 25 Hz |

Bit exact against its model over 112 camera positions, the same test as
chequer4's with `HARRIER_MINP=1`.

## What the eleven scanlines cost

| | T-states |
|---|---|
| 11 scanlines of screen, 128 bytes each at 5.5 | 7,744 |
| 11 more trips round the row loop, at 210 | 2,310 |
| 7 more bands — one a width, and the widths are 1..7 — at 454 | 3,178 |
| 11 more swap masks in `chq4_msk8`, at 81 | 891 |
| **measured** | **+14,527** |

## Why it is not a 50 Hz routine, and why nothing smaller is either

chequer4's worst frame is 118,586 T-states against a 120,000 T-state
50 Hz frame: **1,414 spare**. The cheapest possible step down the screen is
the next width, p=7, which is two scanlines and one band — about 2,350
T-states. So there is no partial extension that fits either. The board
either stops where chequer4 stops, or it goes to the horizon and the frame
goes to 25 Hz. That is a cliff, not a slope.

**At 25 Hz, though, it is cheap.** 129,183 of a 240,000 T-state frame is
54%, where harrier's 25 Hz floor — with the haze, and eleven scanlines
short — was 92%. If the demo is going to be 25 Hz anyway, this is the floor
to use, and there is half a frame left for whatever goes on top of it.

## What it would take to draw 95 scanlines at 50 Hz

The screen itself is 66,880 T-states of the 120,000 and cannot move: 5.5
T-states a byte is the floor, and a compiled `PUSH` run is already at it.
Everything else — 62,300 T-states — is dispatch:

| | T-states | per scanline |
|---|---|---|
| the row loop, 95 × 210 | 19,950 | 210 |
| the band loop, 64 × ~454 | 29,056 | ~307 |
| `chq4_msk8` | 7,807 | 82 |
| the runs' overrun past the row | ~4,180 | ~44 |

so it would have to lose 13,000 T-states, a fifth of it. The band loop is
where it is: 454 T-states to set up a band that is 1.48 scanlines long,
patching six bytes into the row loop from three tables. Two things were
measured and rejected while looking for it:

- **Drawing the far rows only when they change.** They change rarely — the
  phase of a 1-pixel square never moves at all — and over the demo's camera
  path a mean of 3.9 of the 11 need redrawing in a frame. But the worst
  case is all 11, every time the camera crosses a square boundary and every
  stripe flips at once, so the frame that matters is not any cheaper.
- **Giving up per-scanline stripes.** Quantising the depth parity to a
  width band (1-2 scanlines) would take `chq4_msk8` and the row loop's mask
  work with it, about 11,000 T-states. It moves stripe boundaries by up to
  a scanline, which is a change to the picture — and it still would not be
  enough on its own.

## Memory

A viewport change means a new run bank: 9,752 bytes of run and 3,264 of
entry table, against chequer3's 8,722 and 3,204, because the widths now run
1..64 rather than 8..64. That did not fit, and two things made room:

- **`chq4_ztab` holds only the rows that have a board on them** (95 words,
  not 192), which is what `chq4_msk8` reads.
- **The fog table is not in the image at all.** It is a palette gradient
  per scanline — display data the routine never reads — so `tests/mkgif.py`
  now builds it in Python. On a SAM it would live wherever the copper's
  table lives, not in the 8K under the screen.

That leaves 504 bytes spare below 0x2000.

## What the full-depth viewport forced in the shared code

- `chq4_fill`'s haze loop is now inside an `IF CHQ4_TOP > CHQ4_HZ + 1`.
  With no haze rows its counter started at zero, wrapped to 256, and filled
  32K of memory with 0x33 — including the run bank it was about to jump
  into.
- The top run's spill (`CHQ4_SPILL` PUSHes into the row above) now repairs
  with `CHQ4_ABOVE`, which is the haze where there is haze and the sky
  index where the board reaches the horizon.

    HARRIER_MINP=1 python3 tests/mkchq3data.py    # the full-depth run bank
    HARRIER_MINP=1 python3 tests/mkchq4data.py    # and its tables
    python3 tests/test_chequer5.py                # verify and time
