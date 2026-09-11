# chipdis — reading a sound chip backwards

Every synthesis routine in this repo works the same way: a score decides
what to write to the chip each frame. `soundchip/tests/chipdis.py` reads that
backwards. Given nothing but a log of register writes — no source, no
symbols — it recovers what the chip is being made to do.

| | |
|---|---|
| `soundchip/tests/saareg.py` | SAA1099 register logs: the format, the capture hook, and what a frame of them means |
| `soundchip/tests/ayreg.py` | VGM and VGZ files, for the AY-3-8910 — because **a VGM file already is a register log** |
| `soundchip/tests/chipdis.py` | the analysis, which is chip-agnostic, and the report |
| `soundchip/tests/test_chipdis.py` | the only honest test: point it at five routines whose scores are in this repo and check it recovers them |

    python3 soundchip/tests/test_chipdis.py

## What it finds

- **notes** — where each starts, how long it runs, which note and how
  many cents off, and the shape of its amplitude
- **glides** — runs where the pitch moves rather than steps, in cents a
  second, and **whether the period or the frequency was stepped evenly**,
  which says how the player's code was written rather than merely how it
  sounded
- **vibrato** — rate and depth, per note
- **volume patterns** — a repeating amplitude ramp, its rate and depth,
  and **how many frames behind it another channel runs the same one**
- **pairs** — two channels close enough to beat, how fast they beat, and
  whether the detune was written as a divider offset
- **stacks** — one channel at 2f, 3f, 4f or a fifth above another
- **ganging** — several channels carrying one noise generator, which is
  how you get more amplitude steps than a register has
- **the grid** — the frame spacing note starts fall on, and so the tempo

## The two measurements that needed care

**A detune is not best described in cents.** Where a chip divides a
clock, what a composer actually wrote is a *divider*, and a player that
writes the same note to two channels and adds one to the second has
detuned by a different number of cents at every pitch. So the analyser
reports the divider difference when it is consistent: "the dividers
differ by +1, so it was written as one period plus 1" says how the code
works. `strings.z80s` comes back as −3 in the divider, which is exactly
what `ST_DET` is.

**A modulation's rate must come from the peaks, not from a fit.** The
first version fitted a sinusoid across each note and read 11.5 frames
where the table plainly held 12. Two things were wrong with it, and both
are worth knowing:

- a note is not a straight line — `shaku.z80s` bends *into* the note and
  sags out of it on purpose — and taking only a straight line out leaves
  enough of that shape to drag the fitted period several per cent short;
- a vibrato that arrives over four cycles has ragged early ones, because
  the table's values are rounded to whole frequency bytes, and a fit
  over the whole note averages those in.

The fix is a centred moving average to remove the note's shape (no phase
shift, and the depth it flattens is divided back out exactly), then the
**median spacing of the peaks** for the period, and the sinusoid fit only
for the depth. Read off the longest note it reports 12.00 frames — 4.17
Hz — which is what `SK_VIBLEN` says.

## Verified against known answers

A reverse-engineering tool cannot be checked against a model of itself,
so it is checked against routines whose scores are in this repo:

| | it recovers |
|---|---|
| `shaku` | all eleven notes of the phrase by name, every one within 6 cents; the vibrato at **4.17 Hz**; that ch1 is 2f and ch2 is 4f of ch0; that the breath is noise generator 1 in mode 3 |
| `strings` | three detuned pairs, the detune as **−3 in the divider**, beating 1.46 Hz |
| `crow` | the roughness pair at **35 Hz**, and that it is roughness rather than chorus |
| `storm`/`thunder` | that **no tone is enabled anywhere**; that both generators are ganged three channels wide for **46 levels rather than 16**; and the rumble's clock sweeping 298 down to 125 shifts a second |
| `ensemble` | the flute's octave pair surviving the move to three channels, and one noise channel against five tones |

## On other people's music

`ayreg.py` exists because the AY formats — `.ym`, `.vgm`, `.vgz` — *are*
register logs; that is why chip tunes are a few kilobytes. So the same
analyser reads them, and it answers things a spectrum cannot: how many
channels a lead is doubled across, whether the hardware envelope
generator is running, how many frames a portamento takes and whether the
period or the frequency was stepped.

Worked on a real tune (a 128K Spectrum title theme, AY at 1,773,400 Hz),
it found a lead that is two plain square channels with no envelope
generator at all, carrying a ten-frame descending volume ramp with the
second channel running the same ramp five frames behind the first — a
5 Hz tremolo in anti-phase — portamento on nearly every note change of
two to five frames, and the two voices converging to a **one-divider**
detune at cadences. None of that is visible in a spectrogram, and all of
it is three lines of a register log.

## If you pick this up

1. **Capture from hardware or SimCoupe.** `saareg.capture()` is nine
   lines against an emulator's OUT hook, and the same nine work on a
   debugger's watchpoint over ports 255 and 511. The format is text, one
   line a frame.
2. **The envelope generators.** `saareg.State.env()` reports them and
   `ayreg` reports the AY's shape and rate, including whether the rate is
   fast enough to be heard as a tone rather than an envelope — which is
   how an AY "buzzer" bass is made. Nothing in this repo has used the
   SAA's yet.
3. **Turn a log back into a score.** Everything needed to emit a
   `storm.z80s`-style segment list, or a `shaku.z80s` phrase, is already
   in the analysis. That would make it a transcriber rather than a
   report.
