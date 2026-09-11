#!/usr/bin/env python3
"""Score the trackers against a MIDI score of the same performance.

    python3 tests/ground.py source.wav score.mid

Everything in `transcribe.py` was built against spectra and against my own
synthetic cue, and both let a three-halves tempo error and an organ
masquerading as a melody through. A MIDI export of the same performance
settles those questions instead of arguing them: it says what was played,
when, on which instrument, by name.

The alignment is checked first and reported, because a score that is a
different edit of the piece would make every number below meaningless. On
the recording this was built for, 90% of detected onsets land within 60 ms
of a MIDI note start at an offset of -0.04 s, so the two are the same
performance.

For each part it reports, per 20 ms frame where the MIDI part is sounding:
how often the tracker has any pitch at all, how often that pitch is exactly
right, and how often it is right but in the wrong octave - which is worth
separating, because the arranger can move an octave and cannot invent a
note.
"""
import sys

import numpy as np

import smf


def piano_roll(notes, n_frames, rate):
    """A track as one sounding pitch a frame - the highest, where it
    overlaps itself."""
    out = np.zeros(n_frames)
    for q in notes:
        a = int(round(q.start * rate))
        b = max(a + 1, int(round(q.end * rate)))
        for i in range(max(0, a), min(n_frames, b)):
            if q.pitch > out[i]:
                out[i] = q.pitch
    return out


def align(onsets, starts, lo=-6.0, hi=6.0, step=0.02, tol=0.06):
    """The offset that matches the most onsets, and how many."""
    best = (0, 0.0)
    for off in np.arange(lo, hi + step, step):
        d = np.abs(onsets[:, None] - (starts[None, :] + off)).min(axis=1)
        hit = int((d < tol).sum())
        if hit > best[0]:
            best = (hit, float(off))
    return best[1], best[0]


def score(mine, truth, tol=0.5):
    """Tracker against piano roll, where the truth is sounding."""
    n = min(len(mine), len(truth))
    mine, truth = np.asarray(mine[:n], float), np.asarray(truth[:n], float)
    on = truth > 0
    if not on.any():
        return None
    have = (mine > 0) & on
    exact = have & (np.abs(mine - truth) <= tol)
    klass = have & (np.abs(((mine - truth + 6) % 12) - 6) <= tol)
    return {"frames": int(on.sum()),
            "voiced": float(have.sum()) / on.sum(),
            "exact": float(exact.sum()) / on.sum(),
            "class": float(klass.sum()) / on.sum()}


def report(rows):
    print("    %-22s %7s %8s %8s %8s"
          % ("part", "frames", "voiced", "exact", "class"))
    for name, r in rows:
        if r is None:
            print("    %-22s      -" % name)
            continue
        print("    %-22s %7d %7.0f%% %7.0f%% %7.0f%%"
              % (name, r["frames"], 100 * r["voiced"], 100 * r["exact"],
                 100 * r["class"]))


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip())
        return 2
    import soundfile as sf
    import transcribe as T
    rate = 50
    x, sr = sf.read(argv[1], dtype="float32")
    mono = x.mean(axis=1) if x.ndim > 1 else x
    tracks, _tpb, tempos, sigs = smf.read(argv[2])
    print("  the score: %.2f bpm, %s, %d notes over %d tracks"
          % (60e6 / tempos[0][1],
             "/".join(map(str, sigs[0][1:])) if sigs else "?",
             sum(len(t.notes) for t in tracks), len(tracks)))

    mag, fr = T.stft(mono, sr, 4096, sr // rate)
    mag /= max(1e-12, mag.max())
    harm, perc = T.hpss(mag)
    fl = T.flux(perc)
    onsets = np.array(T.onset_peaks(fl)) / float(rate)
    starts = np.array(sorted(q.start for t in tracks for q in t.notes))
    off, hit = align(onsets, starts)
    print("  alignment: %+.2f s, %d of %d onsets within 60 ms (%.0f%%)"
          % (off, hit, len(onsets), 100.0 * hit / max(1, len(onsets))))
    bpm, phase = T.tempo_of(fl, rate)
    print("  tempo: the score says %.2f bpm, the grid says %.2f "
          "(x%.3f - the same grid if that is 2 or 0.5)"
          % (60e6 / tempos[0][1], bpm, (60e6 / tempos[0][1]) / bpm))

    n = len(mag)
    def roll(name):
        for t in tracks:
            if t.name and t.name.lower().startswith(name.lower()):
                return piano_roll([smf.Note(q.start + off, q.end + off,
                                            q.pitch, q.velocity, q.channel)
                                   for q in t.notes], n, rate)
        return np.zeros(n)

    bass = T.track_bass(mono, sr, rate)
    loudest = T.track_viterbi(harm, fr, 250.0, 1600.0)
    struck = T.track_struck(harm, fr, rate=rate)
    to_midi = np.vectorize(lambda f: T.to_midi(f) if f > 0 else 0.0)

    print()
    print("  THE MELODY   (the score calls it a bell)")
    bell = roll("Aftermath Bell")
    report([("the struck line", score(to_midi(struck), bell)),
            ("the loudest line", score(to_midi(loudest), bell))])
    print()
    print("  THE ORGAN")
    organ = roll("4 drawbars")
    report([("the loudest line", score(to_midi(loudest), organ)),
            ("the struck line", score(to_midi(struck), organ))])
    print()
    print("  THE BASS")
    for nm in ("Contrabass", "Moogish"):
        report([(nm, score(to_midi(bass), roll(nm)))])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
