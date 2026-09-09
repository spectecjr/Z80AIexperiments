#!/usr/bin/env python3
"""Verify and time render.z80s against a model of the same rasteriser."""
import sys

from bench import Bench
import raster
from test_democube import Model

BUF = {0x80: 0x8000, 0x20: 0x2000}


def main():
    b = Bench("harness_render.asm", org=0)
    s = b.syms
    recip = list(b.peek(s["t3d_recip"], 256))
    colours = list(b.peek(s["rnd_colour"], 6))
    b.call_regs(s["demo_init"])
    b.call_regs(s["rnd_init"])
    mod = Model()
    bad = 0
    times = []
    frames = 400
    for f in range(frames):
        pts = mod.frame(recip)
        b.call_regs(s["demo_frame"])
        drawn_into = b.peek(s["rnd_back"], 1)[0]      # before the flip
        t, _ = b.call_regs(s["rnd_frame"])
        times.append(t)
        want, faces = raster.render(pts, colours)
        got = b.peek(BUF[drawn_into], raster.STRIDE * raster.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                diff = [i for i in range(len(want)) if got[i] != want[i]]
                print("  MISMATCH frame %d: %d bytes differ, first at %d "
                      "(y=%d x=%d) got %02X want %02X, faces %s"
                      % (f, len(diff), diff[0], diff[0] // raster.STRIDE,
                         (diff[0] % raster.STRIDE) * 2, got[diff[0]],
                         want[diff[0]], faces))
                raster.to_png(got, "/tmp/got%d.png" % f)
                raster.to_png(want, "/tmp/want%d.png" % f)
    print("  %-40s %6d frames, %d mismatches" % ("Z80 buffer against the model",
                                                 frames, bad))
    print()
    print("  rnd_frame    min %d T-states, mean %.0f, max %d"
          % (min(times), sum(times) / len(times), max(times)))
    dt, _ = b.call_regs(s["demo_frame"])
    print("  demo_frame   %d T-states" % dt)
    print("  together     %.0f T-states a frame, %.0f%% of a 6MHz SAM's "
          "120,000" % (sum(times) / len(times) + dt,
                       100 * (sum(times) / len(times) + dt) / 120000))
    # a picture, for the eyeballs
    raster.to_png(b.peek(BUF[b.peek(s["rnd_front"], 1)[0]],
                         raster.STRIDE * raster.H), "/tmp/z80cube.png")
    print("\n%s" % ("ALL TESTS PASSED" if bad == 0 else "FAILURES: %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
