#!/usr/bin/env python3
"""Verify and time storm.z80s, and render what it plays to a .wav.

    python3 tests/test_storm.py
"""
import os
import sys

import numpy as np

from bench import Bench
import storm as S
import saa1099 as A
from test_crow import Chip, spectrogram

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    b = Bench("harness_storm.asm", org=0)
    s = b.syms
    chip = Chip(b)
    model = S.Storm()
    bad = 0

    _, t = b.fast_timed_call(s["sm_init"], 0, 0)
    got = chip.take()
    if got != S.INIT:
        bad += 1
        print("  sm_init wrote %s, wanted %s" % (got, S.INIT))
    print("  %-28s %6d T-states   %d registers" % ("sm_init", t, len(got)))

    b.fast_timed_call(s["sm_play"], 0, 0)
    model.play()
    chip.take()

    stream = []
    tmax = 0
    frames = 0
    while model.playing():
        _, t = b.fast_timed_call(s["sm_frame"], 0, 0)
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
    print("  %-28s %6d T-states   %.2f%% of a 50 Hz frame"
          % ("sm_frame", tmax, 100.0 * tmax / 120000))
    print("  %-28s %6d       %.2f s" % ("frames", frames, frames / 50.0))
    print("  %-28s %6d" % ("register writes checked",
                           sum(len(x) for x in stream) + len(S.INIT)))

    out = A.SAA1099()
    for r, v in S.INIT:
        out.write(r, v)
    for frame in stream:
        for r, v in frame:
            out.write(r, v)
        out.run(1 / 50.0)
    x = out.samples()
    path = os.path.join(ROOT, "demo", "storm.wav")
    A.wav(path, x, mono=True)
    print("  %-28s %s, %.2f s" % ("wav", path, len(x) / A.RATE))

    m = A.dcblock(x.mean(axis=1))
    m /= max(1e-9, np.abs(m).max())
    R = A.RATE

    def bands(lo, hi):
        seg = m[int(lo * R):int(hi * R)]
        sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
        fr = np.fft.rfftfreq(len(seg), 1.0 / R)
        edges = [0, 60, 125, 250, 500, 1000, 2000, 4000, 8000, 22050]
        tot = sp.sum()
        return [(edges[i + 1],
                 100 * sp[(fr >= edges[i]) & (fr < edges[i + 1])].sum() / tot)
                for i in range(len(edges) - 1)]

    thunder = bands(0.4, 7.0)
    rain = bands(9.5, frames / 50.0 - 0.2)
    print("  %-28s %s" % ("the thunder, by band",
                          " ".join("<%d %.0f%%" % b for b in thunder[:5])))
    print("  %-28s %.0f%%" % ("  of it under 250 Hz",
                              sum(v for _, v in thunder[:3])))
    print("  %-28s %s" % ("the rain, by band",
                          " ".join("<%d %.0f%%" % b for b in rain[4:8])))
    print("  %-28s %.0f%%" % ("  of it over 1 kHz",
                              sum(v for _, v in rain[5:])))

    env = np.sqrt(np.convolve(m ** 2, np.ones(R // 20) / (R // 20), "same"))
    peak = env[:int(7 * R)].max()
    print("  %-28s %.2f at %.1f s, and %d rolls after it"
          % ("the rumble", peak,
             np.argmax(env[:int(7 * R)]) / float(R),
             sum(1 for i in range(1, len(S.THUNDER) - 4)
                 if S.THUNDER[i][4] > S.THUNDER[i][3]
                 and S.THUNDER[i][4] > S.THUNDER[i + 1][4])))
    print("  %-28s %.2f" % ("the rain settles at", env[int(12 * R)]))

    print()
    print("  thunder, then rain, as the wav has it:")
    print(spectrogram(m, A.RATE, seconds=len(m) / float(A.RATE), rows=18))

    print()
    print("  %-46s %d" % ("checks that failed", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
