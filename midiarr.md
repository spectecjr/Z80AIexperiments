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

## 3a. Timbre, and what the chip actually has

Asked to make it fuller, the honest inventory of what this chip can do to
its own sound is short. There is no filter. The envelope generators shape
amplitude at a rate this code already drives at 50 Hz, so they buy nothing
a per-frame level does not. What is left is **detuning**, and it is enough.

The SAA1099 divides its clock by 511−n, so the only detune it can express
is an integer change in n, and what that is worth depends where the note
sits: 6.7 cents at 110 Hz for one unit, 3.7 at 1 kHz. Two channels on one
note a unit apart therefore beat at 0.4 Hz down low and 2.2 Hz up high —
which is a chorus.

The mistake worth recording: ch4 was first given the harmony's *top line*
with a detune applied, and the disassembler found **no detuned pair at
all**. A detune only beats against the same note; two channels on two
different notes are just two notes. Doubling the arpeggio in unison instead
gives a pair beating 0.5–6.2 Hz over 8,002 of 8,140 frames at one unit, or
1.0–12.5 Hz at two. One line thickened sounds fuller than two lines bare,
and with a median of three distinct pitches in the score against five tone
channels there is room to spend.

Also added, all of it from the score rather than inferred:

- **velocity.** The bell carries 27 distinct velocities from 92 to 127 and
  the organ 19 from 65 to 101. A fixed level per part threw all of it away.
- **toms as pitched tones.** GM 41, 43, 45, 47, 48 and 50 are toms, and
  reading them as noise loses the only drum in the kit that plays a note.
- **the melody an octave doubled**, and a resting channel lent to whatever
  else is sounding: the melody rests 59% of this score.

| | voices a frame | frames with ≤2 | pairs a frame |
|---|---|---|---|
| the first score-driven version | 2.84 | 52% | 0.92 |
| with the chord recovered | 3.26 | 17% | 1.36 |
| with velocity, fill and chorus | **3.62** | **7%** | 1.89 |

## 3b. Note lengths, measured against the score

Reported: "the MP3 version has a longer decay and a lot of reverb, so the
notes go on longer than the ones driven by the MIDI." Both halves of that
turned out to be measurable, and one of them was the opposite way round:

| | detected | written | ratio |
|---|---|---|---|
| the melody | 0.38 s | 0.31 s | **1.22×** |
| the bass | 0.26 s | 4.50 s | **0.06×** |

The melody over-hangs because a pitch tracker ends a note when the pitch
stops being detectable, and reverb keeps it detectable: a bell's strike
partial stays within 12 dB of its own peak for a further 0.15 s after the
written note-off. `trim_tails` ends a note where its own energy has fallen
to 45% of the peak it reached *inside* the note — a decay, which is what a
player hears as the end — and the ratio becomes **1.02×**.

The bass was worse and in the other direction: a 4.50 s held note was
coming back as a median of 0.62 s, a seventeenth of itself. The cause is a
semitone alternation — measured, `F#1 G1 F#1 G1` across four seconds of one
note — and a median filter on a 50/50 alternation returns whichever side it
fell on, so the note comes apart into dozens of fragments. A **mode** filter
on semitones cannot alternate: at 0.82 s it gave notes 0.92× the written
length *and* raised pitch-class accuracy from 88% to 89%, where a median
filter of the same width got the lengths right and cost 15 points.

Two guards were needed, both found by the other recordings:

- `trim_tails` may not cut a note below 60% of itself, and the drop must
  hold for three frames. Without either, material whose notes do not decay
  went to a median of 0.08 s — the floor — and lost 9 points of coverage.
- the mode window follows the tempo (about half a beat) rather than being
  fixed at 41 frames, which was right for one recording at 80 bpm and took
  9 points off another.

Both measures then read about a point *below* the fragmented version —
fit 51.9% against 52.5%, coverage 58.0% against 58.8% on one recording.
That is the same disagreement as `legato` in `chiparr.md`: a frame-local
measure prefers fragments, because a fragment tracks the moment-to-moment
spectrum more closely than a held note. The score says the held notes are
right, so the score wins.

## 4. What it says about the audio arrangements

The score sounds a median of **three distinct pitches** at once (mean 3.60,
at most 8) against five tone channels, so there is headroom — but not as
much as "add more voices" assumed, and some of what the audio path plays as
separate voices are the partials of notes already sounding elsewhere.

And the perceptual measure prefers the wrong one: the arrangement built
from the exact score scores **48.3%** where the one built from the audio
scores 56.0%. The audio version plays what dominates the recording's
spectrum — the bell's strike partials, the organ's loud mids — and the
score version plays what was written. `percept.md` §5a says the same thing
about a smaller decision; this is the same finding at the scale of a whole
arrangement, and it means the fit number cannot be used to choose between
them.

## 4a. The two arrangements, note for note

`tests/versus.py` puts both register logs against the score they are both
meant to be playing. Per frame it asks two questions, and only one of them
separates them:

    recall     of the pitches the score has sounding, how many does the
               arrangement play
    precision  of the pitches the arrangement plays, how many are in the
               score at all

| | pitches played a frame | recall (any octave) | **precision (any octave)** |
|---|---|---|---|
| from audio | 4.44 | 88% | **80%** |
| from the score | 2.64 | 85% | **97%** |

The score sounds 3.61 pitches a frame. Both arrangements *find* the piece
about equally well — 88% against 85% — and the audio one plays 0.8 pitches
a frame more than the music contains, **a fifth of which are not in the
piece at all.** Recall was never the problem. Invented notes were.

Per channel, that localises:

| channel | sounds | of what it plays, in the score |
|---|---|---|
| bass | 94% | 86% |
| melody | 84% | 91% — but **72% of it is the organ** |
| second voice | 88% | 87% |
| **arpeggio** | **99%** | **64%** |
| third voice | 100% | 76% |

The arpeggio was the single largest inventor: sounding almost always, and
two notes in five absent from the piece — because it was playing a triad
guessed from a chroma profile rather than anything detected. The
score-driven arranger's arpeggio scores 100% on the same measure, for the
one reason that it cycles a pad's *actual* polyphony.

So the audio path does that too now: the arpeggio and the third voice both
take pitches that were really tracked, and both prefer a pitch no other
channel is already playing — measured, the arpeggio had been doubling
another channel in **61%** of its frames, which spends a channel on nothing.
Where nothing was detected the third voice rests, as the score does there.

| | pitches a frame | precision (any octave) | the melody's part |
|---|---|---|---|
| before | 4.44 | 80% | 79% |
| after | 4.07 | 82% | 81% |

Both audio measures read slightly *down* on that change — fit 53.8% → 53.0%,
coverage 58.0% → 55.4% — and the score says it plays fewer invented notes
and more of the melody. The score is the better authority, and this is the
fourth time those two have disagreed.

### A regression, and how it was found

The change above made the arrangement sound worse, and the report was that
some channels seemed to be "playing the wrong part of the piece at the wrong
time". They were not, and the first thing to check was whether they were:
cross-correlating each channel's pitch-class activity against the score over
±5 seconds puts every channel within 0.2 s of where it belongs. Nothing was
shifted.

What the arpeggio was doing instead:

| | first 24 steps |
|---|---|
| before | `A3 A4 C4 C5 E4 E5 A3 A4 C4 C5 E4 E5` |
| after the change | `A4 E6 C5 E6 E4 E6 A4 E6 C5 E6 E4 E6` |
| from the score | `A4 C5 E5 A4 C5 E5 A4 C5 E5` |

**Every other step leapt to E6.** 69% of its intervals were wider than an
octave and 37% wider than two, against a median of 12 semitones and no
two-octave leaps in the score-driven version.

The cause was the pool it drew from. `live` included the high voice, which
lives at 1200–2600 Hz and already has a channel of its own - and because
that pitch was rarely one another channel had taken, the
prefer-something-fresh rule picked it every second step. A rule intended to
stop the arpeggio doubling had turned it into a two-octave saw.

An arpeggio sweeps a chord. The pool is now folded into one octave above its
lowest note and deduplicated by pitch class, so what cycles is a voicing
rather than whatever happened to be tracked: `A4 C5 E4 A4 C5 E4`, median
interval 7 semitones, 2% of steps wider than an octave and none wider than
two.

Worth noting what caught it. Neither audio measure moved much across the
regression or the fix - fit 53.0% then 53.5%, coverage 55.4% then 55.1% -
and `percept.py` is not blind to a two-octave leap in principle; it simply
cannot weigh one against everything else going on. What showed it was
looking at the notes as a sequence, which is the one thing none of the
measures here do.

## 4b. Why the score version holds the tune and the audio one does not

One number:

| the melody channel, against the Bell track | matches its pitch class |
|---|---|
| audio, following the loudest line | **57%** |
| audio, following the struck line | **57%** |
| from the score | **100%** |

The melody channel plays the right note 57% of the time from audio and
always from the score, and neither tracker does better than the other —
both are pulled to the organ, whose C3 and E3 are the loudest components in
the mix at −1 and −2 dB. That is the coherence difference, and it is a
transcription limit rather than an arrangement one: it is the cost of
separating a quiet bell from a loud organ in a finished mix, and a score
does not have to.

## 5. Does any of it transfer to a recording with no score?

Some of it, and it is worth being exact about which.

**Transfers as-is, no score needed.** The tempo fix (scoring a grid by what
it explains, refining the period to a hundredth of a frame, scanning the
whole range); leaving notes unquantised; `legato`; `trim_tails` and the
mode-filtered bass, now that the score has calibrated their thresholds;
and the chip-side chorus, which is arithmetic on register values.

**Transfers, and measured positive.** Dynamics. Audio has no velocities but
it has the energy at each note's start, which is the same information
measured rather than recorded. `loudness_of` uses it: fit 52.2% → 52.5% and
the lead's level spread 1.31 → 1.67, for nothing.

| | fit | peaks | lead level spread |
|---|---|---|---|
| fixed levels | 52.2% | 58.8% | 1.31 |
| **dynamics from the audio** | **52.5%** | 58.8% | **1.67** |

One trap in it: the floor must be high enough that the lead's quietest note
still beats the bass. At 0.55 a lead at level 15 drops to 8 under a bass at
12, and the test for "the lead is the loudest voice" caught that twice, at
46% and then 73% where the rule is 85%. With lead 15 and bass 12 the floor
cannot go below 0.8; it is 0.88.

**Transfers mechanically but not economically.** The chorus. It needs a
spare channel and the audio path has none — it fills all five tone channels
with distinct lines. Taking one for a chorus gives a real pair (0.5–3.5 Hz
over 2,926 frames) and costs:

| | fit | peaks |
|---|---|---|
| five distinct voices | 52.5% | **58.8%** |
| four voices and a chorus | 51.4% | **46.9%** |

Twelve points of coverage for a chorus is a bad trade on these numbers. It
is available as `detune` with `chorus_steals`, off by default.

**Does not transfer.** Which part is the melody. The score settles it by
name; audio does not, and `percept.py` prefers the wrong answer by a point
and a half (`percept.md` §5a). The same for a bell's written octave: the
score says F3–G4 and every spectral method says C6, because that is where a
struck metal tone puts its energy. Both are right about different things,
and only a score knows which one the composer wrote.

## 6. The drums, and a version mismatch

Reported: the drums sound wrong around 38 s. Against the score, the reason
was stark - its drum track runs from 54 s to 108 s, and the arrangement was
placing hits from 12 s to 189 s:

| | score | arrangement |
|---|---|---|
| hits | 339 | 555 |
| span | 54–108 s | 12–189 s |
| **30–40 s** | **0** | **26 snares** |

Drums through 80% of a piece that has drums for 54 seconds. Every hit
outside that window is a bell or an organ chord being struck, because onset
detection cannot tell a drum from the attack of anything else.

**Per-onset classification does not fix it.** Five features were measured
against the score, and against a base rate of 67% for guessing "not a drum"
every time:

| | accuracy |
|---|---|
| spectral flatness of the rise, 2–10 kHz | 76% |
| how many third-octave bands rise together | 69% |
| energy above 8 kHz | 69% |
| the percussive share of the rise | 69% |
| the share of the rise sitting on harmonics | 65% |

Nine points of signal at best. The question was being asked at the wrong
scale: a drum part is **sectional**. It comes in, it plays, it stops. Asked
"does this passage have drums in it" rather than "is this onset a drum", the
high-band percussive flux separates cleanly — 0.0175 in a passage with none
against 0.1525 in one with them — and because the errors are frame-to-frame
noise while the truth is a contiguous block, keeping only runs of four
seconds and closing gaps under two turns an 83% frame classifier into a
usable gate.

555 hits become 310, and 30–40 s goes from 26 to **none**.

### And the recordings are not all the same piece

The gate also marked 120–169 s, which the score says has no drums. It is
right and the score is incomplete: this export has 11 tracks where an
earlier one listed `Sub` and `Linn` — a LinnDrum — and the audio's high-band
percussive energy over that stretch is 0.0953, between the drum section's
0.1525 and the 0.0175 of a passage with nothing in it. There is a second
drum part in the recording that the export does not contain.

Then the composer, looking at the project: the drums run from about 38 s to
73 s. The recording says otherwise, in two independent bands — the
cymbal band is empty until 60 s, and the kick band carries only the
Contrabass, which lives at 40–100 Hz, until 70 s. The MP3 and the MIDI agree
with each other and both differ from the project as it now stands.

Worth stating because it bounds every measurement in this file: the ground
truth here is a recording and an export of one version of one piece, and a
score is only ground truth for the audio it was exported with.
