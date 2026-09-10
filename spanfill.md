# spanfill.z80s — design notes

**What a flat-shaded span costs, measured rather than guessed.** This is the
inner loop any polygonal floor needs — Zarch's landscape, a lit heightfield,
anything that leaves a rasteriser as *from here to here in this colour* —
and the answer decides whether such a thing is a 25 Hz routine or a 12 Hz
one.

| | measured |
|---|---|
| **a span** | **63.0 T-states** |
| **a byte** | **5.51 T-states** — `PUSH`'s floor, so there is nothing under it |
| a scanline | 92 T-states |

Checked bit for bit against `tests/spanfill.py` at 2, 4, 6, 8, 12 and 16
spans across, and the line through the six timings is where the 63.0 comes
from.

| spans a scanline | 128 rows × 128 bytes | of a 25 Hz frame |
|---|---|---|
| 2 | 118,212 | 49% |
| 5 | 150,216 | 63% |
| 7 | 165,588 | 69% |
| 11 | 195,072 | 81% |
| 14 | 222,162 | 93% |

## Why a span is only 63 T-states

    spn_span:
            LD   A,(DE)             ; where in the run this span enters
            INC  DE
            OR   A
            JR   Z,spn_eol
            LD   L,A
            LD   A,(DE)             ; the colour, both pixels of it
            INC  DE
            LD   B,A
            LD   C,A
            JP   (HL)

**The entry.** A run of 64 `PUSH BC` is 64 bytes, one byte a `PUSH`, so
where to jump for n of them is one byte of arithmetic — and the list holds
it worked out already, which makes the dispatch `LD L,A` and `JP (HL)`, four
T-states. The run ends `JP spn_span`, so a span is 53 T-states in and 10
back out.

**The colour.** A MODE 4 byte is two pixels, so a flat colour is the same
byte twice: `LD B,A / LD C,A` and the pair is ready to push.

## What it does not do

**The odd pixel at a span's end.** A `PUSH` is two pixels, so a boundary
lands on an exact pixel only if the byte it falls in carries one pixel of
each colour. That is chequer3's mixed-pair trick, and here it would cost one
more byte in the list and one store a span — call it 20 T-states, an
estimate, on top of the 63.

**Anything above it.** The list has to come from somewhere: an edge walked
down the screen (`renderlit`'s `rndl_edge` is 39 T-states a scanline,
measured) and the arithmetic that turns two edge positions into an entry
byte (~25, an estimate). So a span in a real floor is nearer **127
T-states**, and that is the number that matters — see `demo-ideas.md` §15.

## Invariants

- `SP` walks the screen, so interrupts are off and `spn_sp` holds the
  caller's stack.
- The pointer starts one *past* the row's last byte: `PUSH` writes below
  `SP`.
- Every span is a whole number of `PUSH`es. Two pixels is the grain.
- `spn_chain` must be page-aligned and is entered through `H`, which is set
  once a frame.

    python3 tests/test_spanfill.py   # verify against the model and time it
