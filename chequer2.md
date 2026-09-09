# chequer2.z80s — design notes

The Space Harrier floor with the phase exact to the pixel, and still one
dispatch a scanline. **104,301 T-states — 87% of a 50 Hz frame**, against
`chequer`'s 92,404 with a four-pixel phase and `harrier`'s 221,420 with
everything exact.

Verified bit-exact against `tests/chequer2.py` — pixels and parities — over
28 camera positions, and the model is verified against the exact perspective
formula at every pixel of every row.

## The idea

`chequer` draws a scanline as one compiled run of `PUSH`es, which is one
dispatch a scanline however many squares it holds. But a `PUSH` is four
pixels, so the phase quantises to four and the board sits still and then
jumps as the camera slides:

    row 191, first boundary as camx slides 0..14
      chequer    64  64  64  64  64  64  64  64
      chequer2   64  64  63  63  62  62  61  61

The fix is to compile **four runs per square width instead of one** — t = 0,
1, 2 and 3 pixels of phase. Where a boundary lands inside a `PUSH`, that
`PUSH` carries a pair with a pixel of each colour in the right place. So a
run pushes one of four registers rather than one of two, and the phase is
exact while the dispatch stays at one a scanline.

Both halves of the phase come out of the same product the frame already
computes: `i * camx`, whose high byte is the phase in whole `PUSH`es (which
run entry) and whose top two low bits are the phase in pixels (which of the
four runs).

## AF is a colour, and that is the whole awkwardness

The four push registers have to be **one-byte pushes**, or the run's entry
arithmetic breaks: `PUSH IX` and `PUSH IY` are two bytes each. That leaves
`BC`, `DE`, `HL` and **`AF`**.

`F` cannot be loaded, only popped. So the fourth pair is `POP`ped off its own
address once a scanline — and between that `POP` and the run **nothing may
touch the flags**. `EXX` and `LD SP,HL` do not; `ADD HL,DE` does, so the row
pointer is stepped *after* the run rather than before it. `A` is the other
half of the pair, so the scanline count lives in the alternate set with the
row pointer, and the loop turns round in that set and swaps back to draw.

That last part was the bug: falling back to the top of the row loop with the
alternate set still active means the run pushes the row pointer instead of
the colours, and the first thing to notice is the return address being
overwritten.

## What it costs

| | T-states |
|---|---|
| `chq2_floor` | 87,164 — 93 scanlines |
| `chq2_par8` | 7,019 |
| `chq2_entry` | 8,361 — sixteen square widths |
| **`chq2_frame`** | **min 102,665, mean 104,301, max 105,109** |
| | **87% of a 50 Hz frame** |

So exact phase costs 12,000 T-states a frame over `chequer` — the `POP AF`
and the extra `EXX` pair, about 43 T-states a scanline — and 5,312 bytes of
run against 1,328. It is 2.1× cheaper than `harrier`, which also makes the
*width* exact.

The runs are static data rather than generated at init, which is why
`chq2_init` is only the buffer fill.

## Which of the three to use

| | phase | width | T-states | |
|---|---|---|---|---|
| `chequer` | 4 px | 4 px | 92,404 | 50 Hz, 1.3K of run |
| **`chequer2`** | **1 px** | 4 px | **104,301** | **50 Hz, 5.3K of run** |
| `harrier` | 1 px | 1 px | 221,420 | 25 Hz, no run bank |

`chequer2` is the one to use unless memory is tight: the phase is what moves
when the camera slides, and the width is what the eye does not see.

## Invariants

- All four push registers must be one-byte pushes. `IX`/`IY` are not.
- Nothing between `POP AF` and the run may touch the flags.
- The row loop turns round in the alternate set; swap back before drawing.
- Every boundary in a run is at the same offset, because a square is a whole
  number of `PUSH`es — the generator asserts it. Let the width go odd and
  each run would need more than two boundary pairs, and there are no more
  registers.
- The viewport tables are `chequer`'s and shared: assemble `chequerdata.z80s`
  alongside.

    python3 tests/mkchq2data.py     # regenerate the runs and the table
    python3 tests/test_chequer2.py  # verify and time
