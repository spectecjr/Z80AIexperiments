# strings.z80s — design notes

A string pad out of one SAA1099: **1,097 T-states on a held chord,
0.9% of a 50 Hz frame**.

Verified against `tests/strings.py` — **every OUT, in order, 4,054 of
them** — and rendered to `demo/strings.wav` from that captured stream.

## Interface

| symbol | |
|---|---|
| `st_init` | set the chip up, once |
| `st_play` | start the progression |
| `st_frame` | one 50 Hz frame of it |

Needs `saa.z80s` and `stringsdata.z80s`
(`python3 tests/mkstringsdata.py`).

## Six channels, spent the way a string machine spends them

    ch0 ch2 ch4     the three notes of the chord
    ch1 ch3 ch5     the same three, three frequency units above

**Three units is about a hertz down here, so each pair beats once a
second — measured, 0.91 Hz — and that beating is the whole of what
makes an ensemble sound like more than one player.** It is worth being
clear about why the CPU cannot do it instead: at fifty frames a second
it *could* draw a 1 Hz tremolo, but it would be one tremolo, in step
across the whole chord, and that is a Leslie, not a section. Three
detuned pairs are three independent beats, in the chip, for three
register writes a frame.

**The vibrato is shared but not in phase.** One twelve-entry sine, laid
down twice so the index never has to wrap (`twist.z80s`'s trick), read
at +0, +4 and +8 for the three notes. They wander against each other at
no cost at all: same table, three offsets.

**Chords change legato.** The notes move and the level does not, so
there is one attack at the beginning and one release at the end — which
is what makes it a pad rather than four stabs. The amplitude registers
are written **only when the level actually changes**, so a held chord
is six frequency writes and nothing else.

Both channels of a pair share an octave register, which here is a
convenience rather than a nuisance: the octave byte is just the
octave in both nibbles.

## What it costs

| | T-states | |
|---|---|---|
| `st_frame`, holding a chord | **1,097** | 0.9% of a 50 Hz frame |
| `st_frame`, at its busiest | 2,463 | a chord change: octaves and levels too |
| `st_init` | 1,126 | thirteen registers, once |

Measured on the wav: every chord tone within **27 cents** of the score,
which is the detuned twin and the vibrato, both deliberate.

## Invariants

- `n + DET + VIB_DEPTH` must fit in a byte and `n − VIB_DEPTH` must not
  go below zero; `tests/strings.py` asserts both over every chord.
- The vibrato table is laid down **twice** and read at up to +8: shorten
  it and the third note reads off the end.
- `st_level` starts at 0xFF so the first frame always writes the
  amplitudes.

## If you pick this up

1. **Pan the twins.** Every amplitude byte has the same level in both
   nibbles. Putting each pair's twin to the other side would widen it
   enormously — at the price of the beating happening in the room
   rather than in the mix.
2. **Bow noise.** Enabling noise on a tone channel makes the output
   `tone × (2 − noise)`, which is the tone at full or half amplitude —
   a rough, bowed texture rather than hiss. Untried here.
3. **`ensemble.z80s` runs this on three channels** so a flute can have
   the other three, and `shaku.md` is the flute.

    python3 tests/mkstringsdata.py  # the chords, from the Hz
    python3 tests/test_strings.py   # verify, time, and write the wav
