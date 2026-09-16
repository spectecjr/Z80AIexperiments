# chequer5 — design notes

**The same routine as `chequer4.z80s` with the board drawn all the way to
the horizon, at 50 Hz.** Squares down to a single pixel wide, no haze at
all: 95 scanlines of board where chequer4 draws 84, for **113,659
T-states, 95% of a 50 Hz frame, worst frame included**. There is still no
`chequer5.z80s` — a viewport, a bank and a set of tables — but the bank is
paged now and `CHQ4_PAGED` picks which memory map the shared code uses.

It was a 25 Hz routine until the bank was paged. Two things moved it, and
both are things a flat 64K cannot hold: the swap mask became a lookup
rather than a calculation (6,139), and the row loop became a compiled body
per band and phase (9,359).

| | scanlines | narrowest square | T-states a frame | |
|---|---|---|---|---|
| `chequer4` | 84 | 8 px | 110,835 / **114,656** / 118,586 | 50 Hz |
| **`chequer5`** | **95** | **1 px** | 109,825 / **113,659** / 117,621 | **50 Hz** |
| `chequer5`, before the compiled bodies | 95 | 1 px | 119,179 / 123,018 / 126,985 | 25 Hz |
| `chequer5`, before the mask tables too | 95 | 1 px | 125,343 / 129,183 / 133,151 | 25 Hz |
| `harrier` | 84 | 8 px | 220,394 / **221,451** / 223,413 | 25 Hz |

Bit exact against its model over 112 camera positions, the same test as
chequer4's with `HARRIER_MINP=1`.

## The mask table is not worked out, it is looked up

`chq4_msk8` built the swap mask a scanline every frame — 81 T-states a
row, **7,807** for a 95 row board — by adding `camz` to each row's depth
and keeping bit 8. But bit 8 of `ztab[y] + camz` **does not change when
camz changes by 512, and inverts when it changes by 256**, so the whole
table is a function of `camz mod 512`: there are only 512 of them, and the
camera's own square parity is the same thing as adding 256, so it goes in
the same index.

512 tables of 95 rows on a 128-byte stride is 64K — two pages of a SAM,
which has sixteen. The frame pages one chunk in, copies 95 bytes out of it
with unrolled `LDI`s, and pages the bank back: **7,807 becomes 1,668**, of
which 1,520 is the copy. The copy is there because the window holds the run
bank while the board is being drawn; the two `OUT`s cost 22.

That took the routine into the paged memory map `road2.z80s` uses — the
back buffer at `0x8000` by HMPR, the displayed one not mapped at all, this
code in the 8K a MODE 4 screen leaves spare — which is what makes room for
a 64K table in the first place. `chequer4` and `chequer6` still use the
flat layout; `CHQ4_PAGED` in the harness picks.

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

**That was true of a flat 64K.** The mask tables took 6,139 off it and the
compiled bodies another 9,359, and the cliff is behind us: the worst frame
is 117,621, which is 2,379 inside a 50 Hz one. What follows is what it
took.

**At 25 Hz, though, it is cheap.** 129,183 of a 240,000 T-state frame is
54%, where harrier's 25 Hz floor — with the haze, and eleven scanlines
short — was 92%. If the demo is going to be 25 Hz anyway, this is the floor
to use, and there is half a frame left for whatever goes on top of it.

`chequer6` is this board with a pilot in a jetpack in front of it, for
another 25,528 T-states. See `chequer6.md`.

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

so it had to lose 13,000 T-states, a fifth of it. The band loop is where
it was: 454 T-states to set up a band that is 1.48 scanlines long,
patching six bytes into the row loop from three tables.

**Precomputing those six bytes is not enough.** Of the ~357 T-states a
table would replace, ~78 is the six `LD (nn),A` stores that patch the row
loop, and a table still has to do those *and* read six bytes: ~284 against
~357, so about 4,700 a frame. The stores are the floor, not the
arithmetic — which is why the answer is not to compute the patch faster
but to stop patching.

**So the row loop is compiled instead**, one copy per (band, phase), with
all six baked in — the row's last byte, the value set, the shift and the
run to jump to. The band loop patches one address: the jump the row loop
turns round on. A row costs exactly what it did, one T-state more for the
`DEC B / JP NZ,nn` that replaces the `DJNZ`, and a band costs ~168 instead
of ~454: **9,359 T-states a frame, measured**.

There are 2,080 of those pairs, because the phase of a band of width p is
in `[0, p)` and the widths run 1..64, and a body is 30 bytes. 62K of them,
which is the whole point: it is not a thing a flat 64K can hold.

## The bank is cut by band, so paging is five OUTs

Nothing is duplicated and nothing is paged twice. The board is drawn
widest square first and **a band uses exactly one run**, so bodies and runs
are walked in the same order: a chunk holds the bodies, the runs, the value
sets and the band table for a stretch of bands, and needs nothing from any
other chunk.

| chunk | bands | widths | bytes |
|---|---|---|---|
| 0 | 15 | 64..50 | 30,368 |
| 1 | 22 | 49..28 | 31,092 |
| 2 | 27 | 27..1 | 16,644 |

Every chunk keeps its band table at its foot, so a switch is an `OUT` and
a pointer, and the terminator carries the next chunk's `LMPR`. A frame
pages **five** times — two for the mask table, two to walk the bank, one to
put the first chunk back for the caller's stack — which is 55 T-states.

The trap, and it cost an hour: the terminator goes round the band loop to
be found, and the band loop's first act is to step the phase. Every chunk
switch quietly ate one step, so the phases drifted after the first
boundary and a band eventually indexed past its own table. The switch
gives the step back.

Two things were measured and rejected while looking for the 13,000:

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

**Paged**: three bank chunks, two mask chunks and two screen pairs is 14
pages of 16, or 224K of a 256K machine. The entry tables and the records
are gone entirely — a body bakes the run's entry address and its value
set — and `chq4_ztab` with them, because nothing computes a depth any
more.

What follows is how it fitted when it was flat, which is what `chequer4`
and `chequer6` still do.

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
