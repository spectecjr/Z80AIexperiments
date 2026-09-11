# percept.md — how close does it actually sound?

`tests/percept.py`, `tests/refit.py`, with `tests/test_percept.py`.

## 1. Why the old measure was not good enough

`cover.py` counts how many of the source's spectral peaks have a chip
voice within 60 cents. It is a fair measure of whether the right *notes*
are there and a poor measure of whether the result sounds like the
original. It cannot tell a part 20 dB too quiet from one at the right
level; it counts a peak at 8 kHz as dearly as one at 3 kHz where the ear
is most sensitive; and it says nothing about a component that is inaudible
because something louder is sitting on top of it.

So the arranger was being tuned against a number that does not measure
the thing being complained about.

## 2. The model

A percentage, not a distance, because "57% of peaks covered" and "this is
57% of the way there" are not the same claim and only the second is worth
arguing about:

    fit = 1 − D(candidate, reference) / D(silence, reference)

0% is "no better than silence", 100% is "indistinguishable under this
model". One global gain is fitted on the candidate before comparing,
because an arrangement's absolute level is arbitrary — but it is fitted
**once** over the whole signal, never per segment, or a version that got
the dynamics wrong would score as though it had not.

Two representations are averaged, and the reason is that each is blind to
something the other hears.

**The band model** — 23 ms frames, 34 ERB-spaced bands from 50 Hz to
16 kHz, masking spread asymmetrically across bands (−27 dB per ERB
downwards, −12 dB upwards), an equal-loudness weighting, and cube-root
compression of power.

It cannot hear a semitone: an ERB band at 440 Hz is wider than one. And it
is dominated by the single error a chip can never fix. Measured: a square
standing in for a sawtooth differs from it by 3.5 in the 215 Hz band,
while **removing the melody entirely** changes the 1 kHz band by 0.7. On
its own it scored a correct arrangement 82.6% against 78.2% for one with
no melody in it at all. Four points cannot steer anything.

**The pitch model** — 93 ms frames, a harmonic sum over 8 partials on a
20-cent logarithmic grid from 55 Hz to 3.5 kHz, loudness-weighted by the
candidate pitch, compressed.

A square and a sawtooth at the same note land in nearly the same place
here, so what is left is the notes: a semitone error costs 7.9 points
against the band model's 2.2. Its own blind spot is the octave — a note at
f/2 supplies energy at f, 2f and 3f, so it lights up the candidate at f
too, and on its own this model scored an octave-wrong melody *above* a
correct one.

Together, on a battery of ten known damages, there are no inversions.

## 3. What it says about known damage

A reference built of sawtooth parts; candidates built of **squares**,
because that is the real situation. Each damaged one known way:

| | fit |
|---|---|
| everything right | **80.0%** |
| melody an octave down | 77.9% |
| melody 12 dB too quiet | 76.2% |
| melody an octave up | 75.2% |
| melody a semitone sharp | 75.0% |
| melody missing | 74.8% |
| chord a semitone off | 74.0% |
| bass and melody only | 71.5% |
| bass missing | 69.1% |
| the whole thing an octave up | 66.4% |
| white noise | 36.9% |

The scale is compressed — a correct chip arrangement of this material
cannot exceed about 80% because it is squares against sawtooths — so it is
the **differences** that carry the information, not the absolute figure.
`test_percept.py` asserts the ordering rather than any value, which is the
honest claim to make about it.

## 4. Fitting the arrangement back, segment by segment

`chiparr.py` decides every octave and level by rule: a fold window of
seven semitones, a bass lifted above 60 Hz, an evidence test on the
harmonics, fixed levels per part. Every one of those was arrived at by
measuring, and every one is still applied blind to how the result sounds at
any given moment.

`refit.py` asks instead. For each two-second segment it tries moving each
channel's octave and level, renders the segment through the chip, scores it
against the same segment of the original, and keeps whatever comes closest.

The search is cheap for one specific reason: **on the SAA1099 an octave is
the octave register plus one, with the same frequency byte.** So a
candidate costs an array add, a 12 ms render and a 21 ms score — measured.

Measured over the first 30 s of a recording:

| | fit | peaks covered |
|---|---|---|
| as the rules built it | 50.6% | 53.5% |
| after the refit | **52.7%** | 53.7% |

Both numbers move, and the second one matters more than the first: peak
coverage is not what the search optimises, so it is evidence that the
search found something real rather than learning to game its own
objective. The worst segment in that stretch went from 40.2% to 50.5%.

## 5. The search space has to be small, and here is the proof

The obvious thing to do with a search is give it more room. Measured over
the same 30 s, with the independent peak measure watching:

| search space | fit | peaks covered |
|---|---|---|
| octave ±1, level ±3 | 52.7% | **53.7%** |
| the same, plus muting a voice | 51.7% | 50.7% |
| two octaves either way, plus muting | **52.9%** | 49.0% |

Read the last row carefully. It wins on the number being optimised and
loses 4.5 points on the number that is not. That is a search learning to
game its own objective: given room to move a part two octaves or delete
it, it finds arrangements that please the model and have less of the
recording in them. The middle row is the same thing in smaller print, and
it also lands at a worse optimum than the conservative space despite
strictly containing it — greedy hill-climbing takes the cheap way out when
offered one.

So the space stays at one octave and three levels, and the rule for
changing it is that **both** measures have to move the same way. Without a
second measure that the search cannot see, none of this would have been
detectable: the fit alone says the widest space is best.

It is also the same lesson as `chiparr.md` §1 — a part that goes quiet is a
part the arrangement has lost — arriving this time as a measurement rather
than a judgement.

## 5a. The guard, and the mistake it caught

§5 says the search space has to stay small and that the rule is both
measures moving together. That rule was then not enforced in the code, only
in the choice of space — and the search walked straight through the gap.
Over three whole recordings, every one gained perceptual fit and **lost**
peak coverage:

| | fit | peak coverage |
|---|---|---|
| first recording | 54.3 → 57.2% | 57.4 → **56.2%** |
| second | 56.4 → 61.7% | 47.4 → **41.5%** |
| third | 53.5 → 55.6% | 45.3 → **42.5%** |

A 30 s trial had shown both improving, which is why this was reported as a
clean gain before the whole thing had been run. It was not one: the search
was buying spectral balance with the recording's actual notes.

So the guard is now in `refit.py` rather than in the choice of search
space. A move must not reduce the peak coverage **of its own segment**,
whatever it does for the fit — the search optimises one measure and is
graded by a second it cannot see. Measured on 40 s of the second recording:

| | fit | peaks covered |
|---|---|---|
| no guard | 46.5 → 57.3% | 43.2 → **38.5%** |
| guarded | 46.5 → 54.8% | 43.2 → **45.7%** |
| guarded, 2% slack | 46.5 → 55.7% | 43.2 → 44.4% |

Both move together under the strict guard. The unguarded search's extra 2.5
points of fit were costing 7.2 points of coverage, so that difference was
not an improvement in the arrangement at all.

Re-run over the same three whole recordings with the guard on, every one
improves on both measures:

| | fit | peak coverage |
|---|---|---|
| first recording | 54.3 → **57.2%** | 57.4 → **59.3%** |
| second | 56.4 → **60.7%** | 47.4 → **48.8%** |
| third | 53.5 → **55.4%** | 45.3 → **47.1%** |

The first recording is the one worth noting: the guard cost it *nothing* —
the same 57.2% fit as the unguarded search — and bought 3.1 points of
coverage. The unguarded search had not found a better arrangement there at
all, only a way to keep the fit while shedding notes.

The general lesson, which cost two rounds to learn: a single number is not
enough to steer a search, however well founded that number is. There has to
be a second one the search is forbidden to optimise, and it has to be
checked on the whole piece rather than on a convenient excerpt.

## 5a. The clearest case of the model being wrong

Two arrangements of the same recording, identical in every respect but
which line becomes the melody. The composer's own track list names them:
`Aftermath Bell` and `4 drawbars`.

| the melody is | fit | peaks covered |
|---|---|---|
| the **bell** — the tune | 53.9% | 57.4% |
| the **organ** — the pad | **54.8%** | **58.8%** |

Both measures prefer the organ, and they are not wrong about what they
measure: the organ's C3 and E3 are the loudest components in the whole mix
at −1 and −2 dB, so an arrangement that plays the organ matches the
spectrum more closely than one that plays the bell. It is simply not the
question. An arrangement whose melody is the pad has lost the piece, and no
number here says so.

This is the limit of the approach, stated as plainly as it can be: these
measures are good at catching a tracker that has drifted an octave, a part
that has fallen silent, a grid that is three halves out. They cannot be
asked which part is the tune, and asking them gets the confident wrong
answer, every time, by about a point and a half.

## 6. Where the remaining gap actually is

The refit is worth +2.6 points over a whole recording (54.3% → 56.9%).
That is real and it is small, and the question worth answering is what the
other forty points are made of. Three measurements, all on the same 30 s:

**A ceiling.** `arrange.py` — the spectral matcher, six squares fitted to
the spectrum frame by frame with no musical structure at all and 10.5
register pairs a frame — reaches **54.2%**. The part-based arrangement
reaches 50.2%, and 52.7% after the refit. So the arrangement is within
about one and a half points of what six square waves can be made to do on
this material by direct fitting. The decisions are nearly spent.

**Timbre is worth more than any of it.** Taking the arrangement's register
log and resynthesising the *identical notes* with different waveforms:

| the same notes, as | fit |
|---|---|
| squares | 45.4% |
| sawtooths | 48.3% |
| sine plus two quiet harmonics | **52.0%** |

6.6 points for timbre alone, with every note, level and onset unchanged —
more than twice what the whole per-segment search bought. (These are lower
than the chip's own 50.2% because this crude resynthesis lacks the chip's
amplitude behaviour; the comparison that means something is between the
three rows.) A square's odd harmonics at 1/k are brighter than almost any
instrument in a real mix, and the SAA1099 has no filter. That is the
hardware, and it is most of the gap.

**What the search wants is not always what the listener wants.** Left
free, the search made these systematic choices over a whole recording:

| channel | octave | level |
|---|---|---|
| ch0 bass | **up** in 3,337 frames | +3.3 |
| ch1 lead | down in 404 | **−3.5** |
| ch2 second voice | **down** in 3,745 | −2.0 |
| ch3 arpeggio | **down** in 5,986 | +3.6 |
| ch4 third voice | down in 2,100 | +1.9 |

Moving voices down is consistent with the timbre finding: stacked squares
pile harsh harmonics into the high bands, and the model prefers them out of
the way. But it also took three and a half levels off the **lead** — and a
listener had just asked, in so many words, for the lead to stop
disappearing. The model prefers a spectral balance that buries the melody.

So `refit.py` keeps a list of channels whose level it may raise but never
lower, and ch1 is on it. Measured, that constraint costs 0.2 points of fit
(52.7% → 52.5%) and keeps the lead at level 14.2 instead of 9.9. A
perceptual model is a better judge than peak-counting and it is still not a
musician; the arrangement's intentions are inputs to the search, not things
for it to optimise away.
