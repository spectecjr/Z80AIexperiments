# midiarr.md — the score, and what the trackers got wrong

`tests/smf.py`, `tests/ground.py`, `tests/midiarr.py`.

A MIDI export of one of the recordings arrived after several rounds of
arguing about its contents from spectra. It settles those arguments, and
it says that most of what the audio trackers were reporting was wrong in
one specific way.

## 1. The score

1,431 notes, 11 tracks, **160.00 bpm**, 4/4. The composer's own names:

| track | notes | range | span |
|---|---|---|---|
| 4 drawbars | 609 | G3–A6 | 0–162.8 s |
| **Aftermath Bell** | 179 | **F3–G4** | 18–193.5 s |
| Contrabass | 33 | B1–F3 | 0–54 s |
| Moogish | 55 | A1–D4 | 54–196.5 s |
| Choir, Choir Ahh, Choir Ooh | 72 each | G3–F4 | 54–159 s |
| HQ Metal Kit | 339 | — | 54–108 s |

It is the same performance as the audio: at an offset of −0.04 s, **90% of
the onsets detected in the recording land within 60 ms of a note start in
the score**, and 100% of them in the first third. So the comparisons below
are fair.

## 2. What the trackers get right and wrong

`tests/ground.py`, per 20 ms frame in which the named part is sounding:

| part | tracker | has a pitch | **exact** | right class, wrong octave |
|---|---|---|---|---|
| Bell — the melody | struck | 100% | **0%** | 57% |
| Bell | loudest | 92% | **0%** | 55% |
| 4 drawbars | loudest | 93% | **48%** | 67% |
| 4 drawbars | struck | 96% | 40% | 56% |
| Contrabass | bass | 85% | 10% | 17% |
| Moogish | bass | 96% | 3% | **79%** |

Three things fall out of that table.

**The loudest-salience tracker is the organ.** 48% of its frames are the
organ's exact pitch. The composer heard the result as "the bass and the
mids" and was describing a measurement.

**The octave is almost always wrong and the note itself usually right.**
The bell is in the correct octave in *none* of 4,095 frames while its pitch
class is right in 57% of them; the Moogish bass is right on class 79% of
the time and exact 3%. This is the single largest error in the
transcription, and it is not a pitch error — it is a register error, which
is the cheapest thing on this chip to change and the thing `refit.py`
already searches over.

**A bell's fundamental is not where a bell sounds.** The score writes the
bell F3–G4, 175–392 Hz. Measuring the recording said C6 and D5, and both
were right about what dominates: a struck metal tone puts its strike
partials octaves above the fundamental. No spectral method was going to
report F3 for that note, and an arrangement that plays F3 does not sound
like the bell either. `midiarr.py` lifts the written melody an octave by
default for exactly this reason.

## 3. The arrangement from the score

Same six-channel map as `chiparr.md`, filled from named tracks instead of
trackers. Two things had to be fixed before it was honest:

- **the chord was being thrown away.** A pad track is polyphonic, and
  taking its highest note leaves one line where the harmony is. The
  arpeggio now cycles the widest part's own polyphony, which on this score
  is the organ's 609 notes.
- **the three choir tracks are unisons of each other**, not a chord — the
  same 72 notes over the same span in the same range. Arpeggiating them
  gives one note at a time. The harmony part is whichever track has the
  most notes, not whichever is named first.

| | voices a frame | frames with ≤2 | pairs a frame |
|---|---|---|---|
| before | 2.84 | 52% | 0.92 |
| after | **3.26** | **17%** | 1.36 |

## 4. What it says about the audio arrangements

They are **denser than the music**. The score has three to four parts
sounding at once; the audio-derived arrangement plays 4.3 voices a frame.
Some of those voices were the partials of notes already being played
elsewhere — which is what "too thin, add more voices" led to, and the score
says the thinness was never a shortage of voices.

And the perceptual measure prefers the wrong one: the arrangement built
from the exact score scores **48.3%** where the one built from the audio
scores 56.0%. The audio version plays what dominates the recording's
spectrum — the bell's strike partials, the organ's loud mids — and the
score version plays what was written. `percept.md` §5a says the same thing
about a smaller decision; this is the same finding at the scale of a whole
arrangement, and it means the fit number cannot be used to choose between
them.
