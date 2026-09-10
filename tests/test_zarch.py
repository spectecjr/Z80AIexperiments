#!/usr/bin/env python3
"""Verify and time zarch.z80s against tests/zarch.py.

    pip install z80
    python3 tests/test_zarch.py

Zarch's ground: a chequered plane seen from a camera that turns. The
model is the specification - the same 8.8 arithmetic, the same walk -
so this is a byte for byte check of the screen over a sweep of yaws and
camera positions.
"""
import sys

from bench import Bench
import zarch as Z

BUF = {0x80: 0x8000, 0x20: 0x2000}


def main():
    b = Bench("harness_za.asm", org=0)
    s = b.syms
    it, _ = b.call_regs(s["za_init"])
    print("  za_init %d T-states once, sky and haze into both buffers" % it)
    # the whole sweep of yaws, at cameras inside a cell, on a corner of
    # one, and far enough out that the world coordinates have wrapped
    poses = [(x, z, y) for y in range(0, 256, 11)
             for x, z in ((0, 0), (77, 231), (1021, 4444), (60000, 33))]
    bad = 0
    times = []
    spans = []
    for camx, camz, yaw in poses:
        b.poke(s["za_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["za_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["za_yaw"], bytes([yaw & 255]))
        into = b.peek(s["za_back"], 1)[0]
        t, _ = b.call_regs(s["za_frame"])
        times.append(t)
        want, rows = Z.frame(camx, camz, yaw)
        spans.append(sum(len(r) for r in rows))
        got = b.peek(BUF[into], Z.STRIDE * Z.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  MISMATCH x=%d z=%d yaw=%d: %d bytes, first at %d "
                      "(y=%d x=%d) got %02X want %02X"
                      % (camx, camz, yaw, len(d), d[0], d[0] // Z.STRIDE,
                         (d[0] % Z.STRIDE) * 2, got[d[0]], want[d[0]]))
    n = len(poses)
    mean = sum(times) / n
    print("  %-40s %4d cameras, %d mismatches"
          % ("Z80 against the model, pixels", n, bad))
    print("  %-40s %d rows of ground, %d spans a frame on average"
          % ("which is", Z.H - Z.TOP, sum(spans) / n))
    print()
    print("  za_frame   min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %.0f%% of a 25 Hz frame, %.1f Hz free running"
          % ("which is", mean / 2400, 6e6 / mean))
    print("  %-40s %.1f T-states" % ("a span, all in",
                                     (mean - 60 * 1100) / (sum(spans) / n)))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
