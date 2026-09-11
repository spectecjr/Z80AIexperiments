#!/usr/bin/env python3
"""Check the perceptual metric on errors whose severity is known.

    python3 tests/test_percept.py

percept.py is now what every judgement about the arranger rests on, so it
needs checking harder than the things it judges. The test is an ordering:
a reference built of sawtooth parts, and candidates built of SQUARES -
because that is the real situation, a chip standing in for a record - each
damaged in one known way. The metric must rank them in the order a
musician would.

The two halves are tested separately as well as together, because each has
a blind spot the other covers and the test is what keeps that true:

    the band model   cannot hear a semitone - an ERB band at 440 Hz is
                     wider than one - and is dominated by timbre
    the pitch model  cannot hear an octave - a note at f/2 supplies energy
                     at f, 2f, 3f, so it lights up the candidate at f too

Either alone gets a case badly wrong. Together they have no inversions.
"""
import sys

import numpy as np

import percept

SR = 44100
DUR = 3.0


def tone(f, a, square, t):
    if square:
        return a * np.sign(np.sin(2 * np.pi * f * t))
    out = np.zeros(len(t))
    for k in range(1, 21):
        if f * k < SR / 2.2:
            out += np.sin(2 * np.pi * f * k * t) / k
    return a * out * 2.0 / np.pi


def build(parts, square, t):
    out = np.zeros(len(t))
    for f, a in parts:
        out += tone(f, a, square, t)
    return out


def check(what, got, want, ok):
    print("  %-44s %-24s %s" % (what, got, "ok" if ok else "WANT " + want))
    return 0 if ok else 1


def main():
    bad = 0
    t = np.arange(int(DUR * SR)) / float(SR)
    BASS, CH1, CH2, CH3, MEL = 110.0, 220.0, 277.0, 330.0, 880.0
    full = [(BASS, 0.8), (CH1, 0.25), (CH2, 0.22), (CH3, 0.22), (MEL, 0.35)]
    ref = build(full, False, t)
    chord = full[:4]

    cases = [
        ("everything right", full),
        ("melody an octave down", chord + [(MEL / 2, 0.35)]),
        ("melody 12 dB too quiet", chord + [(MEL, 0.09)]),
        ("melody an octave up", chord + [(MEL * 2, 0.35)]),
        ("melody a semitone sharp", chord + [(MEL * 2 ** (1 / 12.), 0.35)]),
        ("melody missing", chord),
        ("chord a semitone off", [(BASS, 0.8)]
         + [(f * 2 ** (1 / 12.), a) for f, a in chord[1:]] + [(MEL, 0.35)]),
        ("bass missing", full[1:]),
        ("bass and melody only", [(BASS, 0.8), (MEL, 0.35)]),
        ("the whole thing an octave up",
         [(f * 2, a) for f, a in full]),
    ]
    model = percept.Model(SR)
    prep = model.prepare(ref)
    got = []
    for name, parts in cases:
        c = build(parts, True, t)
        got.append((name, percept.compare(ref, c, SR, 1e9, model, prep)[0]))

    print("  THE ORDERING   (reference is sawtooths, candidates are squares)")
    for name, v in got:
        print("    %-34s %5.1f%%" % (name, 100 * v))
    print()

    bad += check("identical audio scores 100%",
                 "%.1f%%" % (100 * percept.compare(ref, ref, SR, 1e9, model,
                                                   prep)[0]),
                 "100%",
                 percept.compare(ref, ref, SR, 1e9, model, prep)[0] > 0.999)
    z = percept.compare(ref, np.zeros(len(t)), SR, 1e9, model, prep)[0]
    bad += check("silence scores 0%", "%.1f%%" % (100 * z), "0%", z < 0.001)
    q = percept.compare(ref, ref * 0.2, SR, 1e9, model, prep)[0]
    bad += check("a quarter of the amplitude still scores 100%",
                 "%.1f%%" % (100 * q), "100% - a gain is fitted", q > 0.99)

    best = got[0][1]
    over = [n for n, v in got[1:] if v >= best]
    bad += check("nothing beats the correct arrangement",
                 ", ".join(over) if over else "nothing does", "nothing",
                 not over)

    # the errors a musician ranks confidently, which the metric must too
    d = dict(got)
    for worse, better in (("melody missing", "melody 12 dB too quiet"),
                          ("melody missing", "melody an octave down"),
                          ("melody a semitone sharp", "everything right"),
                          ("chord a semitone off", "everything right"),
                          ("bass missing", "melody missing"),
                          ("the whole thing an octave up", "bass missing")):
        bad += check('"%s" scores below "%s"' % (worse, better),
                     "%.1f%% vs %.1f%%" % (100 * d[worse], 100 * d[better]),
                     "lower", d[worse] < d[better])

    noise = np.random.RandomState(7).randn(len(t)) * 0.3
    nv = percept.compare(ref, noise, SR, 1e9, model, prep)[0]
    bad += check("white noise scores below every real candidate",
                 "%.1f%% vs worst %.1f%%"
                 % (100 * nv, 100 * min(v for _n, v in got)),
                 "lower", nv < min(v for _n, v in got))

    print()
    print("  THE TWO HALVES, and what each cannot hear")
    ear, pit = model.ear, model.pitch

    def half(which, parts):
        c = build(parts, True, t)
        c = c * percept.fit_gain(ref, c)
        if which == "band":
            R, C, Z = (ear.excitation(ref), ear.excitation(c),
                       ear.excitation(np.zeros(len(t))))
            hop = ear.hop
        else:
            R, C, Z = (pit.pitchgram(ref), pit.pitchgram(c),
                       pit.pitchgram(np.zeros(len(t))))
            hop = pit.hop
        return percept._fit(R, C, Z, hop, SR, 1e9)[0]

    b_right = half("band", full)
    b_semi = half("band", chord + [(MEL * 2 ** (1 / 12.), 0.35)])
    p_right = half("pitch", full)
    p_oct = half("pitch", chord + [(MEL / 2, 0.35)])
    print("    band model:  right %.1f%%, a semitone off %.1f%%  (%.1f apart)"
          % (100 * b_right, 100 * b_semi, 100 * (b_right - b_semi)))
    print("    pitch model: right %.1f%%, an octave off %.1f%%  (%.1f apart)"
          % (100 * p_right, 100 * p_oct, 100 * (p_right - p_oct)))
    bad += check("the pitch model is the one that hears a semitone",
                 "%.1f points vs the band model's %.1f"
                 % (100 * (p_right - half("pitch",
                                          chord + [(MEL * 2 ** (1 / 12.),
                                                    0.35)])),
                    100 * (b_right - b_semi)),
                 "a bigger gap",
                 (p_right - half("pitch", chord + [(MEL * 2 ** (1 / 12.),
                                                    0.35)]))
                 > (b_right - b_semi))
    bad += check("the band model is the one that hears an octave",
                 "%.1f points vs the pitch model's %.1f"
                 % (100 * (b_right - half("band", chord + [(MEL / 2, 0.35)])),
                    100 * (p_right - p_oct)),
                 "a bigger gap",
                 (b_right - half("band", chord + [(MEL / 2, 0.35)]))
                 > (p_right - p_oct))

    print()
    print("  %-44s %d" % ("checks that failed", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
