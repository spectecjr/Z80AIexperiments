# chiparr: a recording as six channels, by its parts

`tests/transcribe.py` and `tests/chiparr.py`, with `tests/test_chiparr.py`.

`arrange.md` describes the other way of doing this: match the spectrum
frame by frame, spending each of the six channels on whichever band needs
it most. That works, and what it produces is recognisable, but it is not
an arrangement — it is a six-point-per-frame sample of a spectrogram, and
it sounds like one. Nothing in it holds a note, because nothing in it
knows there is a note to hold.

This is the other approach, and the one a chip musician would recognise:
work out what the PARTS are, then play the parts.

    audio  ->  transcribe.py  ->  score  ->  chiparr.py  ->  registers
                (bass, lead, chords, drums)      (six channels)

## 1. The channel map

Six channels, fixed roles. Fixed is the point: a channel that changes job
every frame cannot hold a note across one, and holding notes is most of
what makes an arrangement sound like music.

| ch | part | notes |
|----|------|-------|
| 0 | bass, **and the kick** | the kick steals this channel for 5 frames |
| 1 | lead | |
| 2 | the lead an octave up | same frequency byte, octave register + 1 |
| 3 | the chord, arpeggiated | **rests while the lead plays** |
| 4 | the snare's tone | silent otherwise |
| 5 | percussion noise | a fixed noise rate, not ch3's generator |

Three of those deserve an explanation.

**The kick steals the bass channel.** A kick and a bass note land on the
same beat in nearly every bar of nearly every record, so giving each its
own channel spends two of six on one event. Stealing is what a chip
musician does instead: for five frames ch0 stops being the bass and
becomes a tone swept 150 Hz down to 82 Hz, then goes back. On the real
recording measured below this happens 401 times, and it is why ch0 shows 401 glides in a
disassembly where no other channel glides at all.

**The arpeggio rests under the lead.** It did not, at first: it played
throughout, ducked four levels when the lead was sounding. Bass plus lead
plus lead-octave is already three voices, and a fourth running under them
is the difference between an arrangement and a wall. The arpeggio's job
is to fill the lead's gaps, so that is all it does now.

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
| chords | chroma over a beat-aligned window, quality decided by the whole piece | see below |
| drums | per-band **rise** at each onset, per bin, snapped to the sixteenth grid | absolute band energy misreads every hit |

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
| mean | 1.77 | 131 |
| median | 1 | 74 |
| 99th percentile | 13 | 962 |
| worst frame | 31 | 2,294 |

at the **measured** 74 T-states per (register, value) pair from
`saa.z80s`. The worst frame is 1.9% of a 120,000 T-state frame, and the
mean is 0.11%. The spectral arranger in `arrange.md` runs an order of
magnitude above this because it rewrites every channel every frame by
construction.

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
- then the register log is read back with `chipdis.py`, which must find
  ch2 as 2f of ch1, ch5 as noise, glides on ch0 and nowhere else, zero
  frames where the arpeggio overlaps the lead, and D–F–A as the
  arpeggio's three commonest notes.

The three trackers are also checked on signals built to break them: the
weak-fundamental spectrum above, a plain sawtooth that must not be read an
octave *down*, and silence — which produced 132 voiced frames until the
harmonic sum learned to test for energy before taking an argmax of zeros.

## 5. What it still gets wrong

- The lead sounds for 80% of the recording's frames. Some of that is the
  track, which has a near-continuous melody; some of it is the tracker
  following sustained harmonic content that a listener hears as pad. The
  arpeggio's rest rule means the cost of this lands on the arpeggio.
- No hi-hats are found in that recording at all: 401 kicks and 220 snares, and
  nothing classified high. The rise test fixed a bias towards "hat" and
  may now lean the other way on material whose hats are quiet.
- Nothing uses the envelope generators, here or anywhere else in the repo.
  A per-note decay written at 50 Hz is what every part gets instead.
