#!/usr/bin/env python3
"""Verify and time shaku.z80s, and render what it plays to a .wav.

    python3 tests/test_shaku.py

Every OUT is captured off the emulator and checked against
tests/shaku.py - register, value and order, frame by frame, over the
whole phrase. The wav is then made by playing that captured stream
through tests/saa1099.py.
"""
# its tests; the sound routines moved into soundchip/, not the

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
import shaku as K
import saa1099 as S
from test_crow import Chip, spectrogram



def main():
    b = Bench("harness_shaku.asm", org=0, here=HERE, root=ROOT)
    s = b.syms
    chip = Chip(b)
    model = K.Shaku()
    bad = 0

    _, t = b.fast_timed_call(s["sk_init"], 0, 0)
    got = chip.take()
    if got != K.INIT:
        bad += 1
        print("  sk_init wrote %s, wanted %s" % (got, K.INIT))
    print("  %-28s %6d T-states   %d registers" % ("sk_init", t, len(got)))

    b.fast_timed_call(s["sk_play"], 0, 0)
    model.play()
    chip.take()

    stream = []
    tnote = tframe = 0
    frames = 0
    while model.playing():
        _, t = b.fast_timed_call(s["sk_frame"], 0, 0)
        got = chip.take()
        want = model.frame()
        if got != want:
            bad += 1
            if bad < 5:
                print("  frame %d: wrote  %s" % (frames, got))
                print("            wanted %s" % (want,))
        if len(want) > 7:
            tnote = max(tnote, t)
        elif want:
            tframe = max(tframe, t)
        stream.append(got)
        frames += 1
        if frames > 2000:
            break
    print("  %-28s %6d T-states   %.2f%% of a 50 Hz frame"
          % ("sk_frame, a note going", tframe, 100.0 * tframe / 120000))
    print("  %-28s %6d T-states   the octaves as well"
          % ("sk_frame, a note starting", tnote))
    print("  %-28s %6d       %.2f s" % ("frames", frames, frames / 50.0))
    print("  %-28s %6d" % ("register writes checked",
                           sum(len(x) for x in stream) + len(K.INIT)))

    chip_out = S.SAA1099()
    for r, v in K.INIT:
        chip_out.write(r, v)
    for frame in stream:
        for r, v in frame:
            chip_out.write(r, v)
        chip_out.run(1 / 50.0)
    x = chip_out.samples()
    path = os.path.join(ROOT, "demo", "shakuhachi.wav")
    S.wav(path, x, mono=True)
    print("  %-28s %s, %.2f s" % ("wav", path, len(x) / S.RATE))

    # what came out: every note of the phrase, against the score
    m = S.dcblock(x.mean(axis=1))
    m /= max(1e-9, np.abs(m).max())
    R = S.RATE
    W = 4096

    def peak_near(t, want, span=0.06):
        """The strongest partial within span of `want`, at time t."""
        i = int(t * R)
        seg = m[i:i + W] * np.hanning(W)
        sp = np.abs(np.fft.rfft(seg))
        fr = np.fft.rfftfreq(W, 1.0 / R)
        k = (fr > want * (1 - span)) & (fr < want * (1 + span))
        if not k.any() or sp[k].max() <= 0:
            return 0.0
        j = np.argmax(sp[k])
        idx = np.where(k)[0][j]
        a, bb, c = sp[idx - 1], sp[idx], sp[idx + 1]
        return fr[idx] + 0.5 * (a - c) / (a - 2 * bb + c) * (fr[1] - fr[0])

    t = 0.0
    worst = 0.0
    for note, dur in K.PHRASE:
        if note != K.REST:
            want = K.SCALE[note]
            got = peak_near(t + dur / 100.0, want)   # the middle of the note
            cents = 1200 * np.log2(got / want) if got else 999
            worst = max(worst, abs(cents))
        t += dur / 50.0
    print("  %-28s %.0f cents, worst of the %d"
          % ("note pitches, off the score", worst,
             sum(1 for n, _ in K.PHRASE if n != K.REST)))

    # and the vibrato on the opening D4, which arrives over four cycles
    want = K.SCALE[0]
    track = np.array([peak_near(t, want, 0.05) for t in np.arange(0.3, 1.5, 0.02)])
    print("  %-28s %.1f Hz mean, vibrato %.1f Hz, +-%.0f cents"
          % ("the opening D4", track.mean(),
             np.fft.rfftfreq(len(track), 0.02)[
                 np.argmax(np.abs(np.fft.rfft(
                     (track - track.mean()) * np.hanning(len(track))))[1:]) + 1],
             600 * np.log2(track.max() / track.min())))

    print()
    print("  the phrase, as the wav has it:")
    print(spectrogram(m, S.RATE, seconds=len(m) / float(S.RATE), rows=18))

    print()
    print("  %-46s %d" % ("checks that failed", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
