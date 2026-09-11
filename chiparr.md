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
| the same, with the lead folded and brought forward | **57.9%** |

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

- 57.8% peak coverage is not 100%, and it cannot be: five tone voices
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
