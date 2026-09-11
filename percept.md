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
