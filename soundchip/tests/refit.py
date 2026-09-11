#!/usr/bin/env python3
"""Fit an arrangement back to the recording, one segment at a time.

    python3 tests/refit.py source.wav            (uses transcribe + chiparr)

chiparr.py decides every octave and every level by rule: a fold window of
seven semitones, a bass lifted above 60 Hz, an evidence test on the
harmonics, fixed levels per part. Each of those rules was arrived at by
measuring, and each of them is still a rule applied blind to how the
result actually sounds at any given moment.

This asks instead. For each segment of the piece, it tries moving each
channel's octave and level, renders the segment through the chip, measures
it against the same segment of the original with percept.py, and keeps
whatever sounds closest. The rules become the starting point rather than
the answer.

The search is cheap for one specific reason: on the SAA1099 an octave is
the octave register plus one with the SAME frequency byte, so a candidate
costs an array add, a 12 ms render and a 21 ms score.

A search given one measure will find what that measure cannot see, so it
is also handed a second one it is not allowed to optimise: the peak
coverage of `cover.py`, which a move must not reduce in its own segment
whatever it does for the fit. Without that guard, every recording tried
gained perceptual fit and lost coverage - 1.2, 2.8 and 5.9 points - which
is the search buying spectral balance with the recording's actual notes.
With it, both move the same way: measured on 40 s, fit +8.3 and coverage
+2.5, where the unguarded search's extra 2.5 points of fit cost 7.2 points
of coverage.

What it is NOT: a way to make a chip sound like a record. Five squares
against a full mix has a ceiling, and the measurements in percept.md §6 say
where it is - and that most of the remaining gap is timbre, which no
arrangement decision can reach.

Written by Claude (Opus) for the Z80AIexperiments repo.
"""
import sys
import time

import numpy as np

import arrange as A
import chiparr as C
import percept
import saa1099 as S
import transcribe as T

RATE = 50
OCTAVES = (-1, 0, 1)            # in octave-register steps
LEVELS = (-3, 0, 3)
MELODIC = (0, 1, 2, 3, 4)       # ch5 is noise; an octave means nothing there

# The lead's level is not the search's to lower. Left free, it took 3.5
# levels off ch1 across a whole recording - the model prefers the spectral
# balance that makes the melody quieter, and a listener asked for the
# opposite in so many words. So the search gets the octaves and the
# accompaniment's levels, and the arrangement keeps its melody.
NO_QUIETER = (1,)


def segments(n_frames, frames_per):
    for a in range(0, n_frames, frames_per):
        yield a, min(n_frames, a + frames_per)


def refit(out, ref, sr, rate=RATE, segment=2.0, passes=2, model=None,
          octaves=OCTAVES, levels=LEVELS, channels=MELODIC,
          no_quieter=NO_QUIETER, peaks=None, slack=0.0, verbose=True):
    """Search each segment's octaves and levels. Edits `out` in place.

    Returns (before, after) as whole-piece fit fractions.
    """
    model = model or percept.Model(sr)
    ref = np.asarray(ref, float)
    if ref.ndim > 1:
        ref = ref.mean(axis=1)
    per = max(1, int(round(segment * rate)))
    spf = sr // rate                        # audio samples a chip frame
    chosen = 0
    t0 = time.time()

    def held_back(a, b):
        """The measure the search is NOT allowed to see, as a guard.

        Every track tried gained perceptual fit and LOST peak coverage:
        -1.2, -2.8 and -5.9 points. The search was buying spectral balance
        with the recording's actual notes. So a move must not cost coverage
        in its own segment, whatever it does for the fit.
        """
        if peaks is None:
            return 0.0
        hit = tot = 0
        for i in range(a, min(b, len(peaks))):
            vs = out.sounding_hz(i)
            if not vs:
                tot += len(peaks[i])
                continue
            vs = np.array([f * h for f in vs for h in (1, 3, 5, 7, 9)])
            for f in peaks[i]:
                tot += 1
                if (np.abs(1200 * np.log2(vs / f)) < 60.0).any():
                    hit += 1
        return hit / float(max(1, tot))

    def score(a, b):
        """How close this window is now, against the same window of source."""
        frames = out.registers(a, b, absolute=True)
        audio = A.render(frames, rate)
        lo = a * spf
        hi = min(len(ref), lo + len(audio))
        if hi - lo < spf * 4:
            return None
        r = ref[lo:hi]
        c = audio[:hi - lo]
        prep = model.prepare(r)
        got, _ = percept.compare(r, c, sr, 1e9, model, prep)
        return got

    first = None
    for a, b in segments(out.n, per):
        base = score(a, b)
        if base is None:
            continue
        base_guard = held_back(a, b)
        if first is None:
            first = []
        first.append(base)
        best = base
        for _p in range(passes):
            moved = False
            for ch in channels:
                if not out.sounded[ch, a:b].any():
                    continue
                for d_oct in octaves:
                    for d_lvl in levels:
                        if d_oct == 0 and d_lvl == 0:
                            continue
                        if ch in no_quieter and d_lvl < 0:
                            continue
                        keep_o = out.oct[ch, a:b].copy()
                        keep_l = out.lvl[ch, a:b].copy()
                        out.shift(ch, a, b, d_oct, d_lvl)
                        got = score(a, b)
                        ok = (got is not None and got > best + 1e-5
                              and held_back(a, b) >= base_guard - slack)
                        if ok:
                            best, moved, chosen = got, True, chosen + 1
                        else:
                            out.oct[ch, a:b] = keep_o
                            out.lvl[ch, a:b] = keep_l
            if not moved:
                break
        if verbose and (a // per) % 20 == 0:
            print("    %5.1f s   %5.1f%% -> %5.1f%%"
                  % (a / float(rate), 100 * base, 100 * best))
    if verbose:
        print("    %d edits kept, %.0f s" % (chosen, time.time() - t0))
    return chosen


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    import soundfile as sf
    x, sr = sf.read(argv[1], dtype="float32")
    seg = float(argv[2]) if len(argv) > 2 else 2.0
    print("  transcribing %.0f s" % (len(x) / sr))
    sc = T.transcribe(x, sr, RATE)
    out = C.build(sc)
    model = percept.Model(sr)
    mono = x.mean(axis=1) if x.ndim > 1 else x
    import cover
    peaks = cover.source_peaks(argv[1], RATE)

    before = A.render(out.registers(), RATE)
    b0, _ = percept.compare(mono, before, sr, 1e9, model)
    print("  before  %.1f%%" % (100 * b0))
    refit(out, mono, sr, RATE, seg, model=model, peaks=peaks)
    after = A.render(out.registers(), RATE)
    a0, _ = percept.compare(mono, after, sr, 1e9, model)
    print("  after   %.1f%%" % (100 * a0))
    S.wav("/tmp/refit.wav", after, mono=True)
    print("  /tmp/refit.wav")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
