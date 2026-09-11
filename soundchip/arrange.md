# arrange — audio onto six squares

`chipdis` reads a register log and says what the chip is doing.
`soundchip/tests/arrange.py` is the other direction: it takes audio and decides
what to write to an SAA1099, frame by frame, so that what comes out is
as close to the input as six oscillators can manage.

| | |
|---|---|
| `soundchip/tests/arrange.py` | the arranger, and the measurements that judge it |
| `soundchip/tests/mkdemosource.py` | an original cue at full fidelity — saws, filters, resonant metal, a pad — so the reduction can be heard against something that is *not* chip music |
| `soundchip/tests/test_arrange.py` | a synthetic source with known content, and the round trip back through `chipdis` |

    python3 soundchip/tests/mkdemosource.py && python3 soundchip/tests/test_arrange.py

## How it works

Every frame, the source's spectrum becomes band powers on a 1/6-octave
scale, and a greedy matching pursuit picks the chip settings that best
account for it. The atoms are the thing to understand:

**Every (octave, frequency byte) the chip can make is an atom, and its
band vector is the whole odd-harmonic ladder of a square wave** — f, 3f
at a ninth of the power, 5f at a twenty-fifth. Fitting with square atoms
rather than sinusoids is what makes the arrangement honest: you cannot
ask this chip for a sine, so the matcher must not pretend you can. Each
noise setting is an atom too, flat to half its clock rate. That is 1,849
tone atoms and 227 noise atoms.

Four things make the difference between a blur and an arrangement, and
all four were found by measuring, not by taste:

**The gain is quantised to four bits before the residual is taken**, so
what the quantisation loses is offered to the atoms chosen after it.

**Loudness comes from a ten-millisecond window, shape from the bands.**
The band analysis needs a long window to resolve bass pitch — 4,096
samples, which is a semitone at the bottom of the chip's range — and a
long window smears an attack over five frames. Measured: onsets matched
went from 49% to 81% once the two were separated.

**Normalise on a percentile of the strongest band, not on the peak and
not on the total.** On the peak, one transient crushes everything else
into the bottom two levels and onset matching collapses to 12%. On the
total, a single sine asks for six channels' worth of level at one pitch.

**One voice to a band.** Without that rule the matcher spends all six
channels on near-copies of one pitch — measured on a 440 Hz sine: 414,
440, 460, 468, 468 and 440 Hz, all at level 15, which is a cluster
rather than a note and wastes five channels.

## The bug the test caught, which is the interesting one

A 1/6-octave band is 200 cents wide, and **34 of this chip's frequencies
land inside the one band that contains 440 Hz**. To the fit they are
identical, so the pitch it returns is arbitrary to ±100 cents — a
semitone and a half out of tune, on every note. The first arrangement I
rendered had exactly that, and it sounded plausible enough that only the
test caught it.

The fix is not finer bands: at 1/24 of an octave a band near 50 Hz would
be 1.4 Hz wide and the FFT's own resolution is 10.8 Hz. Instead the
*selection* stays on coarse bands, where it is robust, and each chosen
tone atom is then **snapped to the actual spectral peak near it** and
rounded to the nearest frequency the chip can make. Two details matter:
the refinement must use the long window (the short one's bins are 43 Hz,
so a ±100 cent search around 400 Hz is one bin and finds nothing), and
an argmax at the edge of the search window means the real peak is
outside it, so the window widens once and looks again.

Measured after: a 440 Hz sine comes back at 440.1 Hz, +1 cent.

## What it costs, and what it achieves

Measured on two sources — an original 21-second cue written for the
purpose, and a four-minute piece of the repo owner's own music:

| | the cue | a 198 s piece |
|---|---|---|
| error on bands the source has | 5.39 dB | **5.13 dB** |
| energy in bands it does not have | 16% | 14% |
| onsets matched | 67% | 82-88% |
| envelope correlation | 0.47 | 0.49 |
| register writes a frame | 10.3 | 11.8 |
| **playback cost on a SAM** | 1.3% | **1.5% of a 50 Hz frame** |
| log, raw | — | 467 kB, 2.4 kB/s |

Two things that fall out of those numbers:

**The CPU is never the problem.** At 100 Hz control — twice a frame —
a full arrangement costs 1.5% of a 50 Hz frame, measured against the
74 T-states a register pair costs in `saa.z80s`. The log is what grows:
2.4 kB a second raw, which wants delta encoding and streaming for
anything long.

**50 Hz against 100 Hz is nearly a wash**: 5.47 dB against 5.49 on the
same material, with the higher rate a little better on the envelope
(0.49 against 0.46) and a little worse on nothing in particular. The
extra control rate buys transients, not accuracy.

## What it cannot do

- **The 14% that is added is not removable.** It is where the squares'
  own third and fifth harmonics land, and the chip has no filter and no
  duty control to take them off.
- **It can pan but it cannot decorrelate.** A mix with an L/R
  correlation of −0.16 comes back at 0.91: per-atom panning places a
  voice anywhere in sixteen steps a side, but genuine width needs
  *different content* on each side, which means spending separate
  channels on left and right and halving the polyphony.
- **Six voices is six voices.** On dense material the matcher spends
  them on whatever is loudest, which is the right answer and still
  leaves the rest out.
- **Reverb has nowhere to go.** The matcher fits tails with sustained
  squares, which is why the floor and the continuity bonus exist.

## If you pick this up

1. **The envelope generators.** Channels 2 and 5 can be driven by the
   chip's own envelope generators rather than a level, which at audio
   rate gives a sawtooth-ish tone — a second timbre for the atom bank,
   and one no routine in this repo has used.
2. **Transient atoms.** A percussive hit is a pitch-swept tone plus a
   noise burst, and the matcher currently has to rediscover that every
   frame. An atom that *is* a two-frame sweep would cost one channel and
   sound far more like a drum.
3. **Look further than one frame.** The fit is greedy per frame with a
   continuity bonus. A short beam search over four or five frames would
   stop voices being handed about, which is most of what is left of the
   warble.
4. **Emit a score, not a log.** The output is 2.4 kB a second because it
   is raw. Everything needed to emit `storm.z80s`-style segments — or a
   note list for `shaku.z80s`'s player — is already in the analysis.
