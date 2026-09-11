# chiparr: a recording as six channels, by its parts

`tests/transcribe.py` and `tests/chiparr.py`, with `tests/test_chiparr.py`.

`arrange.md` describes the other way of doing this: match the spectrum
frame by frame, spending each of the six channels on whichever band needs
it most. That works, and what it produces is recognisable, but it is not
an arrangement — it is a six-point-per-frame sample of a spectrogram, and
it sounds like one. Nothing in it holds a note, because nothing in it
knows there is a note to hold.

This is the other approach, and the one a chip musician would recognise:
work out what the PARTS are, then play the parts — **all of them, every
frame.**

That last clause is the second version of this design, and it is a
reversal. The first version let parts yield to each other: the arpeggio
rested while the lead played, the drums held a channel of their own, the
lead doubled itself an octave up. It measured **23.7%** of the source's
strong 200–2500 Hz peaks covered by a chip voice within 60 cents (37.6%
counting the odd harmonics a square really does produce), and it was
audibly thin — the melody had holes in it and the mid register was empty
most of the time. A part that goes quiet to make room for another part is
a part the arrangement has lost. So nothing yields now, and the numbers
moved to **57.8%** with 4.45 tone voices sounding in the average frame
against two or three before.

    audio  ->  transcribe.py  ->  score  ->  chiparr.py  ->  registers
                (bass, lead, chords, drums)      (six channels)

## 1. The channel map

Six channels, fixed roles. Fixed is the point: a channel that changes job
every frame cannot hold a note across one, and holding notes is most of
what makes an arrangement sound like music.

| ch | part | notes |
|----|------|-------|
| 0 | bass, **and the kick** | the kick steals this channel for 5 frames |
| 1 | the lead | level 15, folded to one register, with vibrato |
| 2 | the second voice | the lead's own octave where the tracker found none |
| 3 | the chord, arpeggiated | **always**, every frame of every chord |
| 4 | the third voice | falls back to a sustained chord tone |
| 5 | percussion | noise only, at a fixed rate, not ch3's generator |

Four tone voices above the bass, against a median of six strong partials
in the source: a reduction still, but no longer a sketch.

Three of those deserve an explanation.

**The kick steals the bass channel.** A kick and a bass note land on the
same beat in nearly every bar of nearly every record, so giving each its
own channel spends two of six on one event. Stealing is what a chip
musician does instead: for five frames ch0 stops being the bass and
becomes a tone swept 150 Hz down to 82 Hz, then goes back. On the real
recording measured below this happens 401 times, and it is why ch0 shows 401 glides in a
disassembly where no other channel glides at all.

**Nothing falls silent, including between notes.** A voice whose tracking
drops out for a few frames holds its last note at a falling level for up
to ten frames rather than stopping: a note that stops for four frames and
starts again is heard as a fault, not as phrasing. Where a voice has
nothing at all, it takes a fallback — ch2 plays the lead an octave up, ch4
holds the chord's fifth — which is the chip version of reducing a line to
a single tone instead of dropping it.

**The arpeggio runs through every chord.** It did not, at first: it rested
while the lead played, on the reasoning that bass plus lead plus
lead-octave is three voices already. That reasoning was wrong in a way
the measurement caught — the lead sounds for 80% of the recording's
frames, so "rest under the lead" meant "do not play", and the mid register
was empty. The mid register is the part, not the padding.

**ch5's noise rate is fixed, not mode 3.** Mode 3 clocks the noise
generator from the first channel of its group — ch3 for the second group —
and ch3 is running the arpeggio. A snare whose brightness follows the
chord is not a snare. `storm.z80s` wants mode 3 for exactly the opposite
reason; here it is the wrong choice.

## 2. Getting the parts out

| part | method | why not the obvious thing |
|------|--------|---------------------------|
| onsets | spectral flux of the percussive half of an HPSS | |
| tempo | flux autocorrelation, candidates folded, log-normal prior at 110 bpm | the unfolded peak read 96 bpm as 63.8 |
| bass | 16,384-sample window, harmonic sum over 5 partials, then an octave test | see below |
| lead | harmonic salience with the bass's partials suppressed, then Viterbi | a frame-by-frame argmax followed the metal hits |
| the other voices | one line per register, from what the bass and lead leave behind | see below |
| chords | chroma over a beat-aligned window, quality decided by the whole piece | see below |
| drums | per-band **rise** at each onset, per bin, snapped to the sixteenth grid | absolute band energy misreads every hit |

### The lead, and why it sounded like it had vanished

Reported: "around 25 s in, the lead mostly vanishes." Measured, at 25–35 s
the lead channel sounds in **100%** of frames and the peak coverage there
is among the best in the whole recording. Nothing was missing. Three
things were wrong anyway, and all three are about a lead being heard *as*
a lead rather than about whether it is there:

**It was not the loudest voice.** The lead sat at level 12 under a bass at
13. A lead that loses to the bass is a lead the listener reports as
missing while it plays in every frame. It is at 15 now, the bass at 12,
the inner voices at 7 and 5 — the lead is the loudest tone voice in 96% of
the frames it sounds in, 4.8 dB clear of the next.

**It leapt octaves.** The line ran A4 C5 E5 A4 C5 **C6** F5 A4 … **D6** B4
D5 — 122 of its 371 intervals larger than a seventh. That is not a melody
leaping; it is a pitch tracker picking whichever partial is loudest. The
cause was in the tracker: its Viterbi had a single silent state, and
re-entry from silence carried **no pitch penalty**, so silence was a free
teleport between registers. The penalty was 2.0 a semitone — twice the
most any frame can pay — so teleporting was the *only* way the path could
move at all. There is no silent state now: the path is continuous by
construction, single-frame steps are capped at seven semitones, the
penalty is 0.3, and voicing is decided afterwards from the salience along
the path that was chosen.

`fold_lead` then moves each note by whole octaves until it sits within
seven semitones of the melody's local centre — a **centred** median over
four notes either side, because a lagging reference drags behind a melody
that is genuinely climbing and then folds a later note back down, which
invents a leap rather than removing one (measured: 2 leaps became 3 on the
test cue). Every pitch class survives; 122 leaps become 43; the test cue's
own melody, which legitimately spans an octave, comes through untouched.

**It was doing nothing the texture was not.** It has vibrato now — one
frequency byte of movement at 5 Hz, which near the top of the divider
range is about 7 cents — fading in after the eighth frame of a note so
short notes stay clean. That is the cheapest possible way to make one
channel sound like an instrument playing a tune and the other four sound
like accompaniment.

A fourth thing turned up while measuring this: the bass sounded in 63% of
frames where the score had it in 89%, because `decay` ran a long note's
level to zero — a 105-frame note at 0.12 a frame runs out of level before
it runs out of note. Levels now fall to a sustain at 55% of the attack,
not to silence, which also *reduced* the register writes, because a level
that has stopped changing stops being written.

### What the "lead" tracker actually finds

It is not the melody, and this should have been checked three rounds ago.
`track_viterbi` follows the pitch with the strongest harmonic salience, and
in a real mix that is whichever part carries the most energy — usually
something in the middle of the texture. Asked for the top line of one
recording it returned a part centred on A4, G4 and D5, and the person who
wrote the recording heard it as **the bass and the mids**.

The melody is not the highest thing present either. On the same recording,
the highest peak within 20 dB of the loudest sat between 2.3 and 5.9 kHz in
every window measured — harmonics and cymbals, not a line. Nor is it the
highest genuine fundamental: extracting every fundamental per frame by
iterative harmonic subtraction and taking the highest gave C4, D5, G3, A3,
A6, G3, A4 … across fourteen consecutive samples, which is not a part.

So "loudest" does not find it, "highest" does not find it, and no
measurement here could have caught it — a mid part *is* the loudest thing
in the spectrum, so both the perceptual fit and the peak coverage were
satisfied. `tests/probe.py` stops guessing: it tracks the best line in each
of four registers, renders each alone on one channel, and asks.

### What does find it: the line that is struck

Asking got a description of one recording at 45 s — "a high bell sound with
an organ in the background and a drone bass" — and measuring those three
layers says why every rule had failed. At 45.0 s:

| layer | components | level |
|---|---|---|
| drone bass | C2, E2 | −27, −23 dB |
| **organ** | C3, E3, G3, B3, C4, E4, G4 | **−1, −2**, −13, −15, −15, −14, −7 |
| bell | C6 at 46.5 s, D5 at 50 s | **0 dB when struck** |

The organ's C3 and E3 are the loudest components in the whole mix. Any
tracker ranking by energy takes the organ, and the bell is only loudest in
the instant after it is hit.

Which is the discriminator. A bell is **struck** and then decays; an organ
sits. So `transcribe.track_struck` decides a pitch only at onsets, and from
the **rise** in the spectrum at that onset — the part of it that is new —
rather than from the spectrum itself, which is mostly whatever was already
sounding. Onsets come from the flux of that band alone, not of the whole
signal, and the note holds until the next strike, which is the shape a
struck note has anyway.

`test_chiparr.py` keeps the case that caught this: a bell playing an
eight-note tune 12 dB *below* a sustained C–E–G–B organ stack and a drone
bass. The struck tracker returns 7 of the 8 strikes (it misses only the one
at t=0, before the onset detector has any history). The old tracker returns
`G4 G4 G4 G4 G4 G4 G4 G4` — the organ, never moving, 0 of 8.

### The melody as a line, not as a pitch decision a frame

Reported: "the structure keeps getting lost." The cause is visible in the
note list. `notes_of` makes a pitch decision every frame and quantises it
to the grid, so a part holding one note for three seconds comes out as a
long note with three-frame fragments punched through it. Measured on one
recording, the melody's **median event was 0.14 s** inside a part whose
real notes last seconds - the melody was restarting five times a second,
and a restarted note is heard as a stutter rather than as phrasing.

`transcribe.legato` makes a melody out of it in three passes: join adjacent
notes of the same pitch, drop anything still shorter than eight frames and
give its time to the note before it, then hold each note towards the next -
but only across a gap of up to about a beat.

That last limit matters as much as the joining. Holding through every gap
produced melody notes of **16.2 and 16.5 seconds**, because the rule was
filling the rests. A rest is part of the structure; a phrase held through
one is a drone.

| | notes | median | coverage |
|---|---|---|---|
| one recording, as tracked | 501 | 0.14 s | 59% |
| the same, as a melody | **125** | **1.54 s** | 78%, so 22% rests |
| a second recording | 544 → 150 | 0.16 → 0.83 s | 46% → 78% |
| a third, whose melody really is fast | 357 → 312 | 0.42 s → 0.42 s | 83% → 89% |

The third row is the control: a recording whose melody genuinely moves
fast is barely changed, which is what a rule like this has to do to be
trusted.

**And both measures mildly disagree with it.** Applied to every part:

| | fit | peaks covered |
|---|---|---|
| as built | 57.7% | 58.8% |
| with legato everywhere | 57.4% | 56.3% |

Fragments track the source's moment-to-moment spectrum more closely than
held notes do, so a frame-local measure prefers them. Neither `percept.py`
nor `cover.py` has any notion of a note being one event, so neither can
see the difference between a phrase and a stutter - which is exactly what
was being complained about. This is the one change in this file justified
by listening rather than by measurement, and it is applied to the melody
when the melody is what is wanted; `chiparr.build` still takes the score as
tracked, because on these numbers it should.

### A second recording, and what it found

Everything above was measured on one recording, which is how an arranger
ends up fitted to one recording. A second one — a different artist, 94 bpm,
E minor, eighth-note kicks — covered 49.0% against the first one's 57.5%,
and the gap was three defects the first recording could not have shown:

**The bass tracker could not name a low note.** Its candidates were the
FFT's own bins, and at 16,384 samples a bin is 2.7 Hz: a sixth of a
semitone at 300 Hz, but four fifths of one at 58 Hz. A measured B1 came
back as A#1 on every frame it sounded. The candidates are a logarithmic
grid at 15 cents now, with each harmonic collected over its bin's
neighbours so a candidate a few cents off still earns its own energy.
Pitch-class accuracy on that recording's bass went from 6 of 20 seconds to
10 of 20.

**The bass tracker was following the kick.** A kick is a pitch too — 40 to
60 Hz of it — and with eighth-note kicks the bass line came back
alternating E1 with a different note every time, which is the real bass
and the kick taking turns. The drums are found first now and the bass
track is blanked for five frames at each kick, with the note segmenter's
median bridging the gap: leaps wider than a seventh fell from 189 of 841
to 43 of 820.

**Everything was a kick.** 862 kicks against 86 snares and 7 hats. Two
causes: the low band ran 40–140 Hz, which contains a bass note's
fundamental, so every bass attack read as a kick; and the onset threshold
was a fraction of the *global* peak flux, which on a track with even
dynamics passes almost every ripple — 2.81 hits a beat, a hit on nearly
every sixteenth of four minutes. The low band is 40–90 Hz now, a kick must
also out-rise the mid band by half again, and the threshold is local: a
peak must stand above the median flux of the second around it. 2.81 hits a
beat became 2.30, of which the kicks are now a plausible count rather than
90% of everything.

The kick's steal of the bass channel is also adaptive now. At two kicks a
beat a fixed five-frame steal spends 30% of the track with no bass at all,
so the steal is capped at the gap to the next kick: an accent, not a hole.

A third defect was in the *cue*, found by the same change: dropping the
candidate floor to 40 Hz put it just above the cue's sub at D1 (36.7 Hz),
so the octave search piled up against the grid's bottom edge and reported
E1 — two semitones wrong. The floor is 36 Hz.

### The other voices: a register each

One tracker finds one line, and the thing it finds is the melody — which
leaves the inner parts, and in a mix there are several. The bass's and the
lead's harmonic combs are attenuated out of the spectrogram first, so what
the extra tracker sees is only what the first two did not explain.

Assigning the strongest remaining peaks to voices by continuity was tried
first, and it does not work: voice 0 ran E4 – E5 – C5 – C4 – A3 inside ten
seconds, which is not a part, and two voices landed on A3 together because
subtracting a harmonic comb does not stop a candidate 40 cents away from
reclaiming the same note. Giving each voice a **register** — 400–1600 Hz
and 200–700 Hz, claimed in that order, each claim subtracted before the
next — cannot cross and cannot duplicate, and the lines come out
singable.

### The bass, and two ways to be an octave out

Autocorrelation is the obvious tool for a bass and it is the wrong one. A
periodic signal correlates as well at 2T as at T, so the peak picked is an
octave out as often as not — and no tie-break on lag length fixes both
directions. Both were measured on real material:

- taking the **global** argmax read the recording's bass as F1 for nearly
  its whole length, through a chord progression that plainly moves;
- taking the **shortest lag within 85% of the best** read the test cue's
  73.4 Hz saw as D3, and the recording an octave above its real line.

A long-window harmonic sum gets the octave right from where the energy
actually is rather than from a tie. 16,384 samples is a 2.7 Hz bin: 1.1
semitones at the bottom of the bass, half of one at the top, and
parabolic interpolation on the winning bin takes it the rest of the way.

That still leaves one case, and it is the common one in a modern mix. Six
seconds into the recording the ladder runs

    65.4 Hz  -17.8 dB     130.8 Hz   0.0 dB     196.0 Hz  -11.6 dB
    261.6 Hz  -3.8 dB      98.0 Hz -46.5 dB

which is C2 with its fundamental 18 dB down, not C3 with a rumble
underneath — and the harmonic sum picks C3, because C3 is where the energy
is. What settles it is the **odd** harmonics of the candidate an octave
down: 3f/2 and 5f/2 are not harmonics of f at all, so energy there can
only come from the lower note really being played. Here 196 Hz is present
at −11.6 dB and 98 Hz is absent at −46.5 dB, which says C2 and says it is
not C1 either. `test_chiparr.py` keeps a synthetic version of this exact
spectrum as a regression: a tone whose fundamental is 18 dB below its
second harmonic must read 65.4 Hz, and it reads 65.3.

### The chords: a key, not a window

Chord quality was decided per window, on whichever third happened to
sound in it. The test cue's first two bars have no third in them at all,
so they came out D **major** and the arpeggio played F# against a D minor
piece for two bars. Music does not change mode that often: each root now
takes the quality that the whole piece's evidence gives it, weighted by
duration. The cue comes out Dm (744 frames), Am (124), Bb (62), G (62) —
every one of which is diatonic to D minor.

### The drums: rise, not energy

What kind of hit an onset is was decided on how much energy each band held
at that frame. That is wrong twice over: a sustained hi-hat contributes to
the high band whether or not it is part of this hit, and a band three
octaves wide sums more bins than one an octave wide. Both push every
classification towards "hat". It is now the **rise** in each band over the
frames just before the onset, per bin, which is what a hit actually is.

Hits are then snapped to the sixteenth grid, loudest winning a shared
slot. Off-grid hits read as mistakes rather than as feel, and two hits a
frame apart read as one flam nobody played.

## 3. What it costs

On the recording it was developed against — 197 s, 9,898 frames at
50 Hz, 107 bpm, A minor:

| | pairs a frame | T-states |
|---|---|---|
| mean | 2.86 | 212 |
| median | 2 | 148 |
| worst frame | 31 | 2,294 |

at the **measured** 74 T-states per (register, value) pair from
`saa.z80s`. The worst frame is 1.9% of a 120,000 T-state frame, and the
mean is 0.18% — filling the arrangement out from two voices to five, and
then adding vibrato on the lead, cost 1.1 register pairs a frame, which is
to say nothing at all. The spectral arranger in `arrange.md` runs an order of
magnitude above this because it rewrites every channel every frame by
construction.

## 3a. Measuring "thin"

"Too thin" is a judgement, and it was the right one twice about this
arranger. `tests/cover.py` turns it into a number so the next change can
be argued about with measurements:

    python3 tests/cover.py source.wav arrangement.log

Of the strong peaks in the source between 200 Hz and 2.5 kHz — strong
meaning within 12 dB of that frame's loudest peak in that band — what
fraction has a sounding chip voice within 60 cents of it. The chip's odd
harmonics count as well as its fundamentals, because a square wave really
does produce them and a source peak at 3f really is covered by a voice
at f.

| | peaks covered |
|---|---|
| parts that yield to each other | 37.6% |
| parts that never yield | 57.8% |
| the lead folded and brought forward | 57.9% |
| the high register given its own channel | **57.4%** |

and per band, on two recordings:

| | 200–700 Hz | 700–1400 | 1400–2500 |
|---|---|---|---|
| first recording, lead-octave on ch2 | 63.2% | 53.2% | 53.6% |
| first recording, high voice on ch2 | 55.8% | 59.3% | **57.6%** |
| second recording, high voice on ch2 | 44.5% | 48.8% | 50.6% |

The second row is the trade that was taken deliberately, and it is worth
being plain about: giving the high register a channel of its own cost the
low-mid eight points and the total half a point. It was taken because a
high melody line going missing is a part lost, where the low-mid is
covered in part by the lead, the arpeggio and the bass's own harmonics.
The split (1200–2600 Hz for the high voice, 200–700 for the low) was
chosen by sweeping both against all three bands and taking the
configuration whose **worst** band was best rather than whose mean was:
one scoring 70% up high while leaving 49% in the middle has lost a part,
and losing a part is the failure mode.

The third row is worth a note: folding the lead into one register moves
notes out of the octave the tracker found them in, and on its own that
cost 3.5 points. Giving ch2 the lead's *original* octave wherever it had
no voice of its own bought them back, so coherence came for free.

## 4. Checking it

`python3 tests/test_chiparr.py` — 18 checks, and they are musical rather
than spectral, because this path's claim is musical. The source is
`mkdemosource.build()`, an original cue at 96 bpm in D minor whose every
part is known, so each answer is compared with the truth:

- tempo 96.8 against 96;
- the bass note 73.4 Hz — the cue's saw, exactly;
- the lead's eight-note motif recovered **in order**;
- D minor the chord holding the most frames, every root diatonic to it;
- all 39 drum hits on the sixteenth grid;
- the fold must remove leaps without inventing any, and without changing
  a single pitch class;
- then the register log is read back with `chipdis.py`, which must find
  ch2 as 2f of ch1, ch5 as noise, glides on ch0 and nowhere else, the
  arpeggio sounding in every one of the 992 chord frames, D–F–A as its
  three commonest notes, and **4.39 tone voices sounding in the average
  frame** with fewer than 15% of frames down to two or less, the lead the
  loudest tone voice in over 85% of the frames it sounds in, and a long
  bass note still sounding at its own last frame. Those are the checks
  that would have caught the thin version and the buried one.

The three trackers are also checked on signals built to break them: the
weak-fundamental spectrum above, a plain sawtooth that must not be read an
octave *down*, and silence — which produced 132 voiced frames until the
harmonic sum learned to test for energy before taking an argmax of zeros.

## 5. What it still gets wrong

- The second recording sits at 47.4% against the first one's 57.4%, and
  the reason is its bass: its pitch class is right 10 seconds in 20, not
  because the tracker is unstable any more but because the track carries a
  sub *and* a bass line and the two disagree about the octave. The
  arrangement lifts everything under 60 Hz, so the played octave comes out
  right where the class does.
- 57.4% peak coverage is not 100%, and it cannot be: five tone voices
  against a median of six strong partials sets the ceiling, and some of
  those partials are a reverb tail or a cymbal that no square wave is
  going to stand in for.
- The extra voices are tracked per register, which is what stops them
  wandering, but a part that crosses a band edge is handed from one
  channel to another mid-phrase.
- The lead's fold is a judgement about the tracker, not about the music:
  where a composer really did write an octave leap wider than the window,
  it is flattened. The window is deliberately as wide as the test cue's
  own melody so that this costs as little as possible.
- No hi-hats are found in that recording at all: 401 kicks and 220
  snares, and nothing classified high. The rise test fixed a bias towards
  "hat" and may now lean the other way on material whose hats are quiet.
- Nothing uses the envelope generators, here or anywhere else in the repo.
  A per-note decay written at 50 Hz is what every part gets instead.
