#!/usr/bin/env python3
"""Verify and time strings.z80s, and render what it plays to a .wav.

    python3 tests/test_strings.py
"""
import os
import sys

import numpy as np

from bench import Bench
import strings as T
import saa1099 as S
from test_crow import Chip, spectrogram

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    b = Bench("harness_strings.asm", org=0)
    s = b.syms
    chip = Chip(b)
    model = T.Strings()
    bad = 0

    _, t = b.fast_timed_call(s["st_init"], 0, 0)
    got = chip.take()
    if got != T.INIT:
        bad += 1
        print("  st_init wrote %s, wanted %s" % (got, T.INIT))
    print("  %-28s %6d T-states   %d registers" % ("st_init", t, len(got)))

    b.fast_timed_call(s["st_play"], 0, 0)
    model.play()
    chip.take()

    stream = []
    tmax = tmin = 0
    frames = 0
    while model.playing():
        _, t = b.fast_timed_call(s["st_frame"], 0, 0)
        got = chip.take()
        want = model.frame()
        if got != want:
            bad += 1
            if bad < 5:
                print("  frame %d: wrote  %s" % (frames, got))
                print("            wanted %s" % (want,))
        tmax = max(tmax, t)
        tmin = min(tmin, t) if frames else t
        stream.append(got)
        frames += 1
        if frames > 2000:
            break
    print("  %-28s %6d T-states   %.2f%% of a 50 Hz frame"
          % ("st_frame, holding a chord", tmin, 100.0 * tmin / 120000))
    print("  %-28s %6d T-states   octaves and levels as well"
          % ("st_frame, at its busiest", tmax))
    print("  %-28s %6d       %.2f s" % ("frames", frames, frames / 50.0))
    print("  %-28s %6d" % ("register writes checked",
                           sum(len(x) for x in stream) + len(T.INIT)))

    out = S.SAA1099()
    for r, v in T.INIT:
        out.write(r, v)
    for frame in stream:
        for r, v in frame:
            out.write(r, v)
        out.run(1 / 50.0)
    x = out.samples()
    path = os.path.join(ROOT, "demo", "strings.wav")
    S.wav(path, x, mono=True)
    print("  %-28s %s, %.2f s" % ("wav", path, len(x) / S.RATE))

    m = S.dcblock(x.mean(axis=1))
    m /= max(1e-9, np.abs(m).max())
    R = S.RATE

    # every chord, against the score
    t0 = 0.0
    worst = 0.0
    for (names, dur), (notes, _) in zip(T.CHORDS, T.CHORD):
        i = int((t0 + dur / 100.0) * R)
        W = 16384                               # 2.7 Hz bins: the pairs blur
        seg = m[i:i + W] * np.hanning(W)
        sp = np.abs(np.fft.rfft(seg))
        fr = np.fft.rfftfreq(W, 1.0 / R)
        for name in names:
            want = T.PITCH[name]
            k = (fr > want * 0.97) & (fr < want * 1.03)
            got = fr[k][np.argmax(sp[k])]
            worst = max(worst, abs(1200 * np.log2(got / want)))
        t0 += dur / 50.0
    print("  %-28s %.0f cents, worst of the %d"
          % ("chord tones, off the score", worst,
             3 * len(T.CHORDS)))

    # the chorus: how fast the detuned pairs beat, in the middle of a chord
    env = np.sqrt(np.convolve(m ** 2, np.ones(R // 100) / (R // 100), "same"))
    seg = env[int(1.2 * R):int(2.3 * R)]
    seg = seg - seg.mean()
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    fr = np.fft.rfftfreq(len(seg), 1.0 / R)
    k = (fr > 0.3) & (fr < 8)
    print("  %-28s %.2f Hz" % ("the pairs beating", fr[k][np.argmax(sp[k])]))

    print()
    print("  the progression, as the wav has it:")
    print(spectrogram(m, S.RATE, seconds=len(m) / float(S.RATE), rows=16))

    print()
    print("  %-46s %d" % ("checks that failed", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
