#!/usr/bin/env python3
"""Verify and time storm.z80s over the thunder-only score, and render it.

    python3 tests/test_thunder.py

Same routine as test_storm.py - the engine does not change, only the
score - so this checks that the two-layer player is exact over a
different set of segments, and measures how deep the rumble came out.
"""
import os
import sys

import numpy as np

from bench import Bench
import thunder as T
import saa1099 as A
from test_crow import Chip, spectrogram

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    b = Bench("harness_thunder.asm", org=0)
    s = b.syms
    chip = Chip(b)
    model = T.Thunder()
    bad = 0

    _, t = b.fast_timed_call(s["sm_init"], 0, 0)
    got = chip.take()
    if got != T.INIT:
        bad += 1
        print("  sm_init wrote %s, wanted %s" % (got, T.INIT))
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
                           sum(len(x) for x in stream) + len(T.INIT)))

    out = A.SAA1099()
    for r, v in T.INIT:
        out.write(r, v)
    for frame in stream:
        for r, v in frame:
            out.write(r, v)
        out.run(1 / 50.0)
    x = out.samples()
    path = os.path.join(ROOT, "demo", "thunder.wav")
    A.wav(path, x, mono=True)
    print("  %-28s %s, %.2f s" % ("wav", path, len(x) / A.RATE))

    m = A.dcblock(x.mean(axis=1))
    m /= max(1e-9, np.abs(m).max())
    R = A.RATE
    sp = np.abs(np.fft.rfft(m * np.hanning(len(m)))) ** 2
    fr = np.fft.rfftfreq(len(m), 1.0 / R)
    tot = sp.sum()
    edges = [0, 30, 60, 125, 250, 500, 1000, 22050]
    print("  %-28s %s" % ("by band",
                          " ".join("<%d %.0f%%"
                                   % (edges[i + 1],
                                      100 * sp[(fr >= edges[i]) &
                                               (fr < edges[i + 1])].sum() / tot)
                                   for i in range(len(edges) - 1))))
    print("  %-28s %.0f%%" % ("  under 125 Hz", 100 * sp[fr < 125].sum() / tot))
    print("  %-28s %.0f Hz" % ("  where half the energy is below",
                               fr[np.searchsorted(np.cumsum(sp), tot / 2)]))

    env = np.sqrt(np.convolve(m ** 2, np.ones(R // 10) / (R // 10), "same"))
    slow = np.convolve(env, np.ones(int(0.8 * R)) / int(0.8 * R), "same")
    peak = int(np.argmax(slow))
    swells, i = 0, peak                 # rolls, half a second apart at least
    while i < len(slow) - int(0.5 * R):
        w = slow[i:i + int(0.5 * R)]
        j = i + int(np.argmax(w))
        if j > i and slow[j] > 0.15 * slow[peak] and j + 1 < len(slow) \
                and slow[j] >= slow[j + 1]:
            swells += 1
            i = j + int(0.5 * R)
        else:
            i += int(0.25 * R)
    quiet = next((i for i in range(peak, len(slow))
                  if slow[i] < 0.1 * slow[peak]), len(slow) - 1)
    print("  %-28s peak at %.1f s, %d swells after it, quiet by %.1f s"
          % ("the roll", peak / float(R), swells, quiet / float(R)))

    print()
    print("  the rumble, as the wav has it:")
    print(spectrogram(m, A.RATE, seconds=len(m) / float(A.RATE), rows=16))

    print()
    print("  %-46s %d" % ("checks that failed", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
