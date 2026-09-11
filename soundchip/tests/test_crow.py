#!/usr/bin/env python3
"""Verify and time crow.z80s, and render what it plays to a .wav.

    python3 tests/test_crow.py

Every OUT the routine makes is captured off the emulator and checked
against tests/crow.py - the register, the value and the order of them,
frame by frame, over a whole call and then some. The .wav is then made
by playing that same captured stream through tests/saa1099.py, so what
you listen to is the Z80's own output and not a Python impression of
it.
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
import crow as C
import saa1099 as S

FRAMES = 300            # six seconds of them
CALLS = (0, 100, 200)   # when the crow is asked to caw


class Chip:
    """Catches the OUTs and turns them back into (register, value)."""

    def __init__(self, bench):
        self.pairs = []
        self.sel = None
        bench.m.set_output_callback(self.out)

    def out(self, addr, val):
        if addr == S.ADDR_PORT:
            self.sel = val
        elif addr == S.DATA_PORT:
            self.pairs.append((self.sel, val))
        else:
            self.pairs.append(("port %d?" % addr, val))

    def take(self):
        got, self.pairs = self.pairs, []
        return got


def spectrogram(m, rate, seconds=2.2, rows=22, cols=76):
    """The call, drawn in the terminal: log frequency against time."""
    n = int(seconds * rate)
    win = n // cols
    lo, hi = 180.0, 7000.0
    edges = lo * (hi / lo) ** (np.arange(rows + 1) / rows)
    grid = np.zeros((rows, cols))
    for c in range(cols):
        seg = m[c * win:c * win + win]
        if len(seg) < 8:
            continue
        sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
        fr = np.fft.rfftfreq(len(seg), 1.0 / rate)
        for r in range(rows):
            k = (fr >= edges[r]) & (fr < edges[r + 1])
            grid[r, c] = sp[k].sum() if k.any() else 0
    db = 10 * np.log10(grid + 1e-12)
    db -= db.max()
    ramp = " .:-=+*#%@"
    out = []
    for r in range(rows - 1, -1, -1):
        line = "".join(ramp[min(len(ramp) - 1,
                                max(0, int((db[r, c] + 45) / 45 * len(ramp))))]
                       for c in range(cols))
        out.append("  %5d |%s" % (edges[r], line))
    out.append("        +" + "-" * cols)
    out.append("         0%s%.1f s" % (" " * (cols - 6), seconds))
    return "\n".join(out)


def main():
    b = Bench("harness_crow.asm", org=0, here=HERE, root=ROOT)
    s = b.syms
    chip = Chip(b)
    model = C.Crow()
    bad = 0

    _, t = b.fast_timed_call(s["crow_init"], 0, 0)
    got = chip.take()
    if got != C.INIT:
        bad += 1
        print("  crow_init wrote %s, wanted %s" % (got, C.INIT))
    print("  %-28s %6d T-states   %d registers" % ("crow_init", t, len(got)))

    b.fast_timed_call(s["crow_call"], 0, 0)
    model.trigger()
    if chip.take():
        bad += 1
        print("  crow_call wrote to the chip; it should only set state up")

    stream = []                 # (frame, [(reg, val), ...]) for the wav
    busy = quiet = 0
    tbusy = tquiet = tstart = 0
    for f in range(FRAMES):
        if f in CALLS[1:]:      # more calls, to hear them differ
            b.fast_timed_call(s["crow_call"], 0, 0)
            model.trigger()
            chip.take()
        _, t = b.fast_timed_call(s["crow_frame"], 0, 0)
        got = chip.take()
        want = model.frame()
        if got != want:
            bad += 1
            if bad < 5:
                print("  frame %d: wrote %s" % (f, got))
                print("            wanted %s" % (want,))
        if want:
            busy += 1
            tbusy = max(tbusy, t)
        else:
            quiet += 1
            tquiet = min(tquiet, t) if quiet > 1 else t
            tstart = max(tstart, t)
        stream.append(got)

    print("  %-28s %6d T-states   %.2f%% of a 50 Hz frame"
          % ("crow_frame, cawing", tbusy, 100.0 * tbusy / 120000))
    print("  %-28s %6d T-states   %d frames of the %d"
          % ("crow_frame, silent", tquiet, quiet, FRAMES))
    print("  %-28s %6d T-states   the LFSR, once a caw"
          % ("crow_frame, starting a caw", tstart))
    print("  %-28s %6d" % ("frames that sounded", busy))
    print("  %-28s %6d" % ("register writes checked",
                           sum(len(x) for x in stream) + len(C.INIT)))

    # and now listen to it: the captured stream, through the chip
    chip_out = S.SAA1099()
    for r, v in C.INIT:
        chip_out.write(r, v)
    for frame in stream:
        for r, v in frame:
            chip_out.write(r, v)
        chip_out.run(1 / 50.0)
    x = chip_out.samples()
    path = os.path.join(ROOT, "demo", "crow.wav")
    S.wav(path, x, mono=True)      # both channels are the same
    print("  %-28s %s, %.2f s" % ("wav", path, len(x) / S.RATE))

    # what came out, measured: the caw should be rough, and the energy
    # should sit where a crow's does rather than where a square wave's does
    m = S.dcblock(x.mean(axis=1))       # as the wav has it: no DC, and
    m = m / max(1e-9, np.abs(m).max())  # the chip's output is unipolar
    R = S.RATE
    env = np.sqrt(np.convolve(m ** 2, np.ones(R // 200) / (R // 200), "same"))
    caw = m[:int(0.36 * R)]
    sp = np.abs(np.fft.rfft(caw * np.hanning(len(caw)))) ** 2
    fr = np.fft.rfftfreq(len(caw), 1.0 / R)
    edges = [300, 600, 1200, 2400, 4800]
    print("  %-28s %s" % ("energy in the first caw",
                          " ".join("%d-%d %.0f%%"
                                   % (edges[i], edges[i + 1],
                                      100 * sp[(fr >= edges[i]) &
                                               (fr < edges[i + 1])].sum()
                                      / sp.sum())
                                   for i in range(len(edges) - 1))))
    body = env[int(0.06 * R):int(0.30 * R)]
    mod = body - body.mean()
    msp = np.abs(np.fft.rfft(mod * np.hanning(len(mod))))
    mfr = np.fft.rfftfreq(len(mod), 1.0 / R)
    k = (mfr > 8) & (mfr < 250)
    print("  %-28s %.0f Hz, %.0f%% deep"
          % ("roughness of the caw", mfr[k][np.argmax(msp[k])],
             100 * mod.std() / body.mean()))

    print()
    print("  the first two calls, as the wav has them:")
    print(spectrogram(m, S.RATE))

    print()
    print("  %-46s %d" % ("checks that failed", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
