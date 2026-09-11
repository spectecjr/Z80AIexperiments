# soundchip — everything to do with making noise

The SAA1099 work, kept apart from the rest of the repository because it
shares nothing with it but the Z80 test harness.

    soundchip/
      *.z80s        the sound routines, and their data tables
      *.md          a design note per routine, and per tool
      demo/         the wavs those routines produce
      tests/        the toolchain, and the tests that verify it

`USING.md` is the manual for converting a recording. Start there.

## The Z80 routines

| | |
|---|---|
| `saa.z80s` | the shared register writer — 74 T-states a (register, value) pair, measured |
| `crow.z80s` | a crow, from two noise generators and a tone |
| `shaku.z80s` | a shakuhachi: f, 2f, 4f and a breath channel |
| `strings.z80s` | a triad, and the same triad detuned three dividers above it |
| `ensemble.z80s` | both of those at once, three oscillators each |
| `storm.z80s` | distant thunder and rain, noise generators only |

Each has a `.md` beside it with the measured costs and what was tried and
dropped. `costs.md` in the repository root collects the T-state figures.

## The toolchain, in `tests/`

Tools and tests sit together, as they do in the repository's own `tests/`.

**The chip, and its register logs**

| | |
|---|---|
| `saa1099.py` | the emulator: four-times oversampled, windowed-sinc decimated |
| `saareg.py` | the register-log format, and capture from a running Z80 |
| `chipdis.py` | reads a register log back and describes it musically |
| `ayreg.py` | the same for AY, out of VGM/VGZ files |
| `smf.py` | a MIDI reader, no library needed |

**Making an arrangement**

| | |
|---|---|
| `chipify.py` | **the command**: a recording or a score in, registers out |
| `transcribe.py` | audio to a score: bass, melody, other voices, chords, drums |
| `chiparr.py` | that score onto six channels |
| `midiarr.py` | a MIDI score onto six channels, which needs no transcription |
| `arrange.py` | the older spectral matcher, kept for comparison |
| `refit.py` | fits each segment back to the recording by search |

**Measuring it**

| | |
|---|---|
| `percept.py` | how close two pieces of audio sound, as a percentage |
| `cover.py` | how many of the source's notes are present |
| `ground.py` | the trackers against a MIDI score of the same performance |
| `versus.py` | two register logs against the score they both mean to play |
| `probe.py` | one line per register, rendered separately, so a person can say which is the tune |

`stems.md` covers feeding it separated stems (Demucs and the like), what
that fixes and what it does not.

`percept.md` is worth reading before trusting any of those numbers. The
short of it: they catch an octave error, a silent part or a grid three
halves out, and they cannot tell you which part is the melody.

## Running the tests

    cd soundchip/tests && python3 test_crow.py

Ten of them. Six assemble and time the Z80 routines and check every OUT
against a Python model of the same routine; four check the toolchain.

They use the repository's `tests/bench.py` to assemble and time — that is
shared Z80 machinery, not audio, so it stayed where it was. The tests pass
it their own root, because their INCLUDEs live here.
