# chequer3.z80s — design notes

**harrier's screen, drawn out of compiled runs, in half the time.** Every
boundary on its exact pixel — both the width of a square and the phase —
at **110,556 T-states, 92% of a 50 Hz frame**, against harrier's 221,420,
which is a 25 Hz routine.

The test does not check it against a model of its own: it checks it against
`tests/harrier.py`, over 56 camera positions, pixels and parities. Same
bytes, twice the rate.

| | phase | width | T-states | |
|---|---|---|---|---|
| `chequer` | 4 px | 4 px | 92,404 | 50 Hz, 1.3K of run |
| `chequer2` | 1 px | 4 px | 104,301 | 50 Hz, 5.3K of run |
| **`chequer3`** | **1 px** | **1 px** | **110,556** | **50 Hz, 12K of run** |
| `harrier` | 1 px | 1 px | 221,420 | 25 Hz, no run bank |

(`chequer` and `chequer2` draw 93 scanlines of board from a 4-pixel horizon;
`chequer3` and `harrier` draw 84 from an 8-pixel one with haze above it.
That difference is worth about 9,000 T-states, and it is why chequer3 is
only 6,000 dearer than chequer2 while doing strictly more.)

## Why it was not obvious that this could work

A compiled run bakes the pattern into instructions, so it can only be shared
by scanlines whose pattern is the same. Exact widths look like they destroy
that sharing: every row has its own width, and there are 57 of them. The
three things that make it fit:

**The phase never exceeds one square.** harrier's phase is
`camx * p / 256`, which is in `[0, p)` — so a run only has to hold
`ceil(p/4)` entry points, and `k = ceil(p/4) - 1 - (phase >> 2)` always
lands inside it. No modulo, no wrap, no second run for the wrapped case.
That is the whole reason the bank is 12K rather than 30K.

**Two pixels of phase are one byte.** Starting SP one byte down the row
moves everything the run pushes two pixels left, for free. So a width needs
two runs (odd pixel of phase) rather than four, which halves the bank again.
The cost is the row's last byte, which a shifted run no longer reaches: the
row loop stores it, and where the run *does* reach it the store is patched
to `LD A,n` and thrown away.

**Six values can be pushed, not four.** `BC` and `DE` are the two colours;
`HL`, `AF`, `IX` and `IY` carry a PUSH with a boundary inside it. An odd
width needs all four, because consecutive boundaries land at every offset
inside a PUSH in turn; an even width needs two. `PUSH IX`/`PUSH IY` are two
bytes where the others are one, which is why the entry table holds addresses
rather than offsets — the arithmetic that chequer2 could do, this cannot.

## The awkwardness

`AF` is a colour, so `F` is loaded by `POP AF` once a scanline and **nothing
between that POP and the run may touch the flags** — `EXX`, `LD SP,HL` and
`INC SP` do not; `ADD HL,DE` does, so the row pointer steps after the run.
`A` is the other half of that pair, so the scanline count and the row
pointer live in the alternate set and the loop turns round in it.

`IX` and `IY` being colours means neither can be the band-table pointer or
the run's return, so the band pointer is a self-modified `LD HL,nn` and the
runs end with `JP chq3_ret`.

The row pointer points at the row's **last byte**, not one past it, so that
the shifted case is `LD SP,HL` and the unshifted one `LD SP,HL / INC SP` —
one patched byte, and the last-byte store needs no `DEC HL`/`INC HL` around
it.

## Where the time goes

| | T-states |
|---|---|
| the screen itself, 84 rows × 128 bytes at 5.5 | 59,136 |
| the run's overrun past the row (see below) | ~4,000 |
| the row loop, 84 × 129 | ~10,800 |
| the band code, 57 × ~490 | ~28,000 |
| `chq3_par8` | 7,019 |
| **`chq3_frame`** | **min 106,913, mean 110,556, max 114,546** |

The band code is the surprise: 57 bands for 84 rows means a band is 1.5 rows,
so its ~490 T-states amortise to ~330 a row. Halving it would be worth more
than anything left in the row loop. The obvious route is to stop patching
seven bytes into the row loop per band and have the row loop read them, but
every register is spoken for and `SP` is already carrying the four pairs.

The overrun is the run's tail past the 64th PUSH: entering at `k` pushes
`64 + (phase >> 2)` PUSHes, and the extra ones land in the row above, which
is drawn afterwards because the board is drawn bottom upwards. Only the
topmost row's overrun needs repairing, into the haze — `CHQ3_SPILL` PUSHes
at `chq3_bend`.

## Memory

8,722 bytes of run and 3,204 of entry table do not fit in one piece. The
free memory is in two blocks either side of the screen buffers, so the
generator fills the top one (**0xE000 to 0xFE00 — it stops there to leave
the stack somewhere**) and puts the rest below. Nothing outside
`mkchq3data.py` cares which run went where: the entry tables hold absolute
addresses.

## Invariants

- Nothing between `POP AF` and the run may touch the flags.
- All four boundary registers must survive the run: the band code may use
  `IX`/`IY` freely, the row loop may not.
- The board is drawn bottom upwards, or the overrun eats the row below.
- The run bank must stay clear of the stack.
- The geometry is harrier's and shared with it: change `tests/harrier.py`
  and both change together.

    python3 tests/mkchq3data.py     # regenerate the runs and the tables
    python3 tests/test_chequer3.py  # verify against harrier and time
