# HANDOVER.md — where the sound work stands

For whoever picks this up next, including a later version of me with none of
the conversation in front of it. Everything below is measured unless it says
otherwise.

## 1. What this is

A toolchain that turns a recording, or a MIDI score of one, into an SAA1099
register log — 50 writes a second of chip registers, which is what a SAM
Coupé would be fed to play the thing. The rendered wav is only how you
listen to it here; the `.log` is the deliverable.

Start at `README.md` for the file map and `USING.md` for the command.

## 2. The state of it, measured today

| recording | bpm found | fit | peaks covered | pairs a frame | drum hits |
|---|---|---|---|---|---|
| Aftermath | 80.00 | 53.7% | 55.0% | 1.94 | 400 |
| Slightly Jarreing | 130.00 | 52.4% | 43.1% | 1.95 | 17 |
| Ethereum 12 | 70.00 | 58.0% | 47.6% | 2.57 | 997 |

Two of those tempi are confirmed against the composer's own MIDI exports:
Aftermath's score says 160 bpm and 80 is its eighth-note grid, the same
grid; Jarreing's says 130.00 exactly. All 10 tests in `tests/` pass, as do
the 33 in the repository's own `tests/`.

## 3. The single most important thing to understand

**Every measurement in this repository can be satisfied by the wrong
arrangement.** This is not a caveat, it is the central finding, and it cost
several rounds to learn:

- `percept.py` and `cover.py` both **prefer an arrangement whose melody is
  the pad** over one whose melody is the tune, by about a point and a half.
  On the recording with a score, playing the organ as the melody scores
  54.8%/58.8% and playing the bell — the actual tune — scores 53.9%/57.4%.
  The organ's C3 and E3 are the loudest components in the mix at −1 and
  −2 dB, so an arrangement that plays them matches the spectrum better. It
  is simply not the question being asked.
- Both measures are **frame-local**, so neither can see melodic coherence.
  An arpeggio leaping two octaves every other step moved them by 0.5 of a
  point. What caught that was looking at the notes as a sequence.
- A search given one measure **will** find what that measure cannot see.
  `refit.py` improved its own objective while *losing* note coverage on
  every track until it was given `cover.py` as a guard it cannot optimise.

Corollary: four defects in a row were found by the composer's ear and not by
any number here — the melody being the mids, the notes ringing too long, the
arpeggio out of time, the drums in the wrong place. **When the ear and the
numbers disagree, the ear has been right every time so far.**

## 4. The pipeline, and where each part's error lives

    audio ──> transcribe.py ──> chiparr.py ──> registers ──> refit.py
    MIDI  ──> smf.py ────────> midiarr.py ──┘

Measured against a score, per 20 ms frame in which each part sounds:

| part | tracker | has a pitch | exact | right class, wrong octave |
|---|---|---|---|---|
| the bell (the melody) | struck | 100% | **0%** | 57% |
| the bell | loudest | 92% | **0%** | 55% |
| the organ | loudest | 93% | **48%** | 67% |
| Contrabass | bass | 85% | 10% | 17% |
| Moogish | bass | 96% | 3% | **79%** |

Read that as: **the notes are mostly right and the octaves mostly are not.**
That is a register error, which is the cheapest thing on this chip to change
and is what `refit.py` searches over.

And the two arrangements compared note for note (`versus.py`):

| | pitches a frame | recall (any octave) | precision (any octave) |
|---|---|---|---|
| from audio | 4.07 | 86% | 82% |
| from the score | 2.64 | 85% | **97%** |

Both *find* the piece equally well. The audio one **invents** — a fifth of
what it plays is absent from the piece. Recall was never the problem.

## 5. What is known to be wrong, in priority order

1. **Which line is the melody.** The melody channel plays the right note 57%
   of the time from audio and 100% from a score, and `--melody struck` does
   no better than the default because both trackers are pulled to whatever
   is loudest. This is the largest error in the pipeline and nothing
   measurable here distinguishes the cases. `probe.py` exists to ask a
   person. See `chiparr.md` and `midiarr.md` §4b.
2. **Jarreing's lead.** Its score has a part named `Lead Rhodes`, and the
   tracker follows `Knife` instead — 75% exact on Knife against 38% on
   Rhodes. A second labelled instance of (1), not yet acted on.
3. **The Jarreing MIDI aligns at only 21%** of onsets within 60 ms, against
   Aftermath's 90%. Either that mixdown differs from the MP3 more than
   expected or the piece is loose. Unresolved, and everything measured
   against that score inherits it.
4. **Timbre.** 6.6 points separate squares from soft tones on *identical*
   notes, against 2.1 for the entire per-segment search. The chip has no
   filter and its envelope generators only shape amplitude at a rate the
   code already drives at 50 Hz, so detuning is the whole toolbox — and in
   the audio path a chorus costs a voice, measured at 12 points of coverage.
5. **The recordings and the scores are not all the same version.** One
   export omits a `Linn` drum track the audio plainly contains; the composer
   reports drums at 38–73 s where both the MP3 and its MIDI put them at
   54–108. A score is ground truth only for the audio it was exported with.

## 6. Design rules that were arrived at by measurement

Do not undo these without re-measuring — each replaced something that
sounded worse:

- **Every part identified keeps its channel.** Parts yielding to each other
  measured 37.6% peak coverage against 57.8%.
- **Notes are not quantised.** The music is hand-played; snapping cost both
  measures.
- **Musical quantities are floats until the moment of use.** The same
  rounding bug appeared three times — the grid, the chord window, and the
  arpeggio's step. The arpeggio's version had it at a fixed 12.5 Hz against
  the music, landing on the beat grid 16% of the time where chance is 32%.
- **The arpeggio cycles detected pitches**, folded into one octave and
  deduplicated by class. A guessed triad was the largest single source of
  invented notes.
- **The lead may be made louder and never quieter** by any search, and its
  dynamics floor must keep its quietest note above the bass.
- **Drums are sectional.** Five per-onset features scored 65–76% against a
  67% base rate. What works is whether low-band and high-band transients
  co-occur, which is what a kit does and a bright synth does not.

`costs.md` §5 in the repository root holds the negative results with their
numbers — a dozen things that were tried and measured worse.

## 7. Things a new session will not have

- **The composer's recordings and scores are not in this repository, by
  intent.** They live in the session's upload directory, which does not
  survive. Ask for them again; the work cannot be reproduced without them.
- The rendered MP3s sent during the session are likewise gone. `chipify.py`
  regenerates them.
- `demucs` and `torch` were installed into the container, not the repo. They
  reinstall from PyPI, but their pretrained weights are blocked by the
  proxy here — see `stems.md`.

## 8. Working practices this repository is held to

- Every Z80 routine is verified **bit-exactly** against a Python model of
  itself, by capturing every `OUT` from the emulated machine.
- **Only measured T-states appear in the documentation.** An estimate must
  say it is one.
- A `.md` note beside every routine and every tool, carrying the numbers and
  the things that were tried and dropped.
- The composer's music stays out of the repository.
