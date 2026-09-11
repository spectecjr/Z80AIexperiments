#!/usr/bin/env python3
"""Verify and time ensemble.z80s, and render what it plays to a .wav.

    python3 tests/test_ensemble.py
"""
import os
import sys

import numpy as np


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)           # soundchip/, with the sources
sys.path.insert(0, HERE)
# bench.py is the repository's Z80 harness runner, shared by all of its
# tests. Only the sound routines moved into soundchip/, not the machinery
# that assembles and times them, so the path to it is spelled out here.
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "tests"))

from bench import Bench
import ensemble as E
import shaku as K
import strings as T
import saa1099 as S
from test_crow import Chip, spectrogram



def main():
    b = Bench("harness_ensemble.asm", org=0, here=HERE, root=ROOT)
    s = b.syms
    chip = Chip(b)
    model = E.Ensemble()
    bad = 0

    _, t = b.fast_timed_call(s["en_init"], 0, 0)
    got = chip.take()
    if got != E.INIT:
        bad += 1
        print("  en_init wrote %s, wanted %s" % (got, E.INIT))
    print("  %-28s %6d T-states   %d registers" % ("en_init", t, len(got)))

    b.fast_timed_call(s["en_play"], 0, 0)
    model.play()
    chip.take()

    stream = []
    tmax = 0
    frames = 0
    while model.playing():
        _, t = b.fast_timed_call(s["en_frame"], 0, 0)
        got = chip.take()
        want = model.frame()
        if got != want:
            bad += 1
            if bad < 5:
                print("  frame %d: wrote  %s" % (frames, got))
                print("            wanted %s" % (want,))
        tmax = max(tmax, t)
        stream.append(got)
        frames += 1
        if frames > 2000:
            break
    print("  %-28s %6d T-states   %.2f%% of a 50 Hz frame, for two voices"
          % ("en_frame", tmax, 100.0 * tmax / 120000))
    print("  %-28s %6d       %.2f s" % ("frames", frames, frames / 50.0))
    print("  %-28s %6d" % ("register writes checked",
                           sum(len(x) for x in stream) + len(E.INIT)))

    out = S.SAA1099()
    for r, v in E.INIT:
        out.write(r, v)
    for frame in stream:
        for r, v in frame:
            out.write(r, v)
        out.run(1 / 50.0)
    x = out.samples()
    path = os.path.join(ROOT, "demo", "ensemble.wav")
    S.wav(path, x, mono=True)
    print("  %-28s %s, %.2f s" % ("wav", path, len(x) / S.RATE))

    m = S.dcblock(x.mean(axis=1))
    m /= max(1e-9, np.abs(m).max())
    R = S.RATE
    W = 16384

    def near(t, want, span=0.04):
        i = int(t * R)
        seg = m[i:i + W] * np.hanning(W)
        sp = np.abs(np.fft.rfft(seg))
        fr = np.fft.rfftfreq(W, 1.0 / R)
        k = (fr > want * (1 - span)) & (fr < want * (1 + span))
        return (fr[k][np.argmax(sp[k])], sp[k].max()) if k.any() else (0, 0)

    # both voices, at the same moment, are where the two scores say
    worst = 0.0
    checked = 0
    t = 0.0
    for note, dur in K.PHRASE:              # the flute
        if note != K.REST and dur > 20:
            f, _ = near(t + dur / 100.0, K.SCALE[note])
            worst = max(worst, abs(1200 * np.log2(f / K.SCALE[note])))
            checked += 1
        t += dur / 50.0
    t = 0.0
    for names, dur in T.CHORDS:             # and the chord under it
        for name in names:
            f, _ = near(t + dur / 100.0, T.PITCH[name])
            worst = max(worst, abs(1200 * np.log2(f / T.PITCH[name])))
            checked += 1
        t += dur / 50.0
    print("  %-28s %.0f cents, worst of %d, both voices"
          % ("everything, off the score", worst, checked))

    print()
    print("  the flute over the pad, as the wav has it:")
    print(spectrogram(m, S.RATE, seconds=len(m) / float(S.RATE), rows=20))

    print()
    print("  %-46s %d" % ("checks that failed", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
