# stems.md — source separation, and what it would and would not fix

Asked whether Meta's **Demucs** could be used here. (Demucs, not Demux —
Hybrid Transformer Demucs, the music source separator: a mix in, four stems
out, drums / bass / other / vocals, or six with `htdemucs_6s` which adds
guitar and piano. MIT licensed, `pip install demucs`.)

Yes, for two of the three problems that have cost the most work here, and
no for the third — which happens to be the expensive one.

## What it would fix

**The drums.** Deciding whether a passage even has drums took four attempts
in this repository, all documented in `midiarr.md` §6: five per-onset
features that scored between 65% and 76% against a 67% base rate; a
sectional gate on high-band percussive energy, which marks a fixed
proportion of any piece and so can never say "none"; the amount of that
energy, which is *nineteen times higher* in a piece with no drum track than
in one with drums; and finally a correlation between low-band and high-band
transients, which works but is a proxy for what a separator gives directly.

A drums stem removes the question. Measured, with stems synthesised from a
score so the drum stem's contents are known exactly:

| | hits | span | within 60 ms of a real hit |
|---|---|---|---|
| from the mix | 400 | 52–162 s | **40%** |
| from a drums stem | 237 | **54–108 s** | **95%** |
| what the score has | 339 | 54–108 s | |

**Read that 95% carefully.** The stem was made *from* the score, so it is
circular as an accuracy figure — it demonstrates the mechanism and the
ceiling, not what Demucs would score on a real mix. The span, though, is the
part that matters and is not circular: from the mix the drums smear across
110 seconds of a piece that has them for 54, and from a stem they do not.

**The bass.** Against a score, the bass tracker on a full mix gets the pitch
class right 85% of the time and the exact octave 3%. Most of that error is
other instruments in the same band: an organ's low notes, a kick's thump,
and a sub-oscillator an octave below the written note. A bass stem removes
all three.

## What it would not fix

**Which part is the melody**, which is the largest measured error in the
whole pipeline: the melody channel plays the right note 57% of the time from
audio against 100% from a score (`midiarr.md` §4b). A bell and an organ both
land in `other`. Six-stem Demucs adds guitar and piano, and neither of those
is a bell, an organ, a Rhodes or a "Knife".

Separation answers "what kind of instrument is this" and the question here
is "which of these is the tune" — which a listener answers instantly, a
score answers by name, and no separator answers at all.

## Using it

`chipify.py --stems DIR` reads `drums.wav`, `bass.wav`, `other.wav` and
`vocals.wav` from a directory, any subset, at the mix's own sample rate —
which is the layout Demucs writes:

    python3 -m demucs -o stems song.mp3
    python3 soundchip/tests/chipify.py song.mp3 \
        --stems stems/htdemucs/song

Each stem present replaces a piece of guesswork: the drum stem is taken as
the drum part with no gate at all, the bass stem is what the bass tracker
runs on, and `other` is where the melody is looked for.

**It is not run from here.** `demucs` and `torch` install from PyPI without
trouble, but the pretrained weights come from `dl.fbaipublicfiles.com` and
`huggingface.co`, and this environment's proxy refuses both with a 403. The
stem *reading* is tested, with stems built from a score; the separation
itself has to happen on a machine that can reach the weights.

Demucs on CPU runs at roughly real time or slower, so a three-minute track
is a few minutes before `chipify` even starts — which is still well inside
the hour the composer said he would wait.
