#!/usr/bin/env python3
"""Verify and time cubes.z80s against tests/cubes.py.

Four lit cubes bouncing in a drawn room, compared byte for byte with
the model every frame - which checks the physics, the ordering, the
room and four cubes' worth of renderlit at once.

    pip install z80
    python3 tests/test_cubes.py
"""
import sys

from bench import Bench
import cubes as C
import raster

BUF = {0x80: 0x8000, 0x20: 0x2000}
PAL = [(36 * i, 13 * i, 9 * i) for i in range(8)] \
    + [(9 * i, 15 * i, 36 * i) for i in range(8)]


def main():
    b = Bench("harness_cubes.asm", org=0)
    s = b.syms
    recip = list(b.peek(s["t3d_recip"], 256))
    lite = [x - 256 if x > 127 else x for x in b.peek(s["rndl_lite"], 3)]
    it, _ = b.call_regs(s["cb_init"])
    print("  cb_init   %d T-states once, both buffers and the room" % it)

    sc = C.Scene()
    bad, times, shown = 0, [], None
    frames = 300
    for f in range(frames):
        into = b.peek(s["rndl_back"], 1)[0]
        t, _ = b.call_regs(s["cb_frame"])
        times.append(t)
        sc.step()
        want, order, _ = sc.draw(recip, lite)
        got = b.peek(BUF[into], raster.STRIDE * raster.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  MISMATCH frame %d: %d bytes, first at %d (y=%d x=%d) "
                      "got %02X want %02X, order %s"
                      % (f, len(d), d[0], d[0] // raster.STRIDE,
                         (d[0] % raster.STRIDE) * 2, got[d[0]], want[d[0]],
                         order))
        elif f == frames - 1:
            shown = got
    n = len(times)
    print("  %-40s %6d frames, %d mismatches"
          % ("Z80 buffer against the model", frames, bad))
    print()
    print("  cb_frame     min %d T-states, mean %.0f, max %d"
          % (min(times), sum(times) / n, max(times)))
    print("  %-40s %.0f%% of 240,000 (25 Hz on a 6 MHz SAM)"
          % ("mean", 100 * (sum(times) / n) / 240000))
    print("  %-40s %.1f Hz mean, %.1f Hz worst"
          % ("which at 6 MHz is", 6e6 / (sum(times) / n), 6e6 / max(times)))
    if shown is not None:
        raster.to_png(shown, "/tmp/z80cubes.png", PAL)
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
