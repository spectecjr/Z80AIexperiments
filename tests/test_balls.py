#!/usr/bin/env python3
"""Verify and time balls.z80s against tests/balls.py.

    pip install z80
    python3 tests/test_balls.py
"""
import sys

from bench import Bench
import balls as B
import raster

BUF = {0x80: 0x8000, 0x20: 0x2000}
N = raster.STRIDE * raster.H
PAL = [(32 * i, 32 * i, 30 * i) for i in range(8)] + [(0, 0, 0)] * 8


def main():
    b = Bench("harness_balls.asm", org=0)
    s = b.syms
    it, _ = b.call_regs(s["bl_init"])
    print("  bl_init   %d T-states once, both buffers blanked" % it)
    print("  formation %d balls on a cube of %d, %d away, %d rows a ball"
          % (B.NBALLS, B.S, B.TZ, B.BH))

    m = B.Balls()
    want = {0x80: bytearray(N), 0x20: bytearray(N)}
    bad, times, shown = 0, [], None
    frames = 256
    for k in range(frames):
        into = b.peek(s["bl_back"], 1)[0]
        t, _ = b.call_regs(s["bl_frame"])
        times.append(t)
        m.frame(want[into])
        got = b.peek(BUF[into], N)
        if got != bytes(want[into]):
            bad += 1
            if bad <= 3:
                d = [i for i in range(N) if got[i] != want[into][i]]
                print("  MISMATCH frame %d: %d bytes, first at %d "
                      "(y=%d x=%d) got %02X want %02X"
                      % (k, len(d), d[0], d[0] // raster.STRIDE,
                         (d[0] % raster.STRIDE) * 2, got[d[0]],
                         want[into][d[0]]))
        elif k == 100:
            shown = got
    n = len(times)
    print("  %-40s %6d frames, %d mismatches"
          % ("Z80 buffer against the model", frames, bad))
    print()
    print("  bl_frame     min %d T-states, mean %.0f, max %d"
          % (min(times), sum(times) / n, max(times)))
    print("  %-40s %.0f%% of 120,000 (50 Hz on a 6 MHz SAM)"
          % ("mean", 100.0 * (sum(times) / n) / 120000))
    print("  %-40s %.0f T-states a ball"
          % ("which is", (sum(times) / n) / B.NBALLS))
    print("  %-40s %.1f Hz mean, %.1f Hz worst"
          % ("at 6 MHz", 6e6 / (sum(times) / n), 6e6 / max(times)))
    if shown is not None:
        raster.to_png(shown, "/tmp/z80balls.png", PAL)
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
