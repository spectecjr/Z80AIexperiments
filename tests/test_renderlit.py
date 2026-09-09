#!/usr/bin/env python3
"""Verify and time renderlit.z80s against a model of the same rasteriser.

Draws 400 demo frames into the Z80's back buffer and compares them byte
for byte with rasterlit.py, and reports how often the plane-based
visibility test disagrees with the screen-space cross product that
render.z80s uses.

    pip install z80
    python3 tests/test_renderlit.py
"""
import sys

from bench import Bench
import raster
import rasterlit
from test_democube import Model

BUF = {0x80: 0x8000, 0x20: 0x2000}
PAL = [(36 * i, 13 * i, 9 * i) for i in range(8)] \
    + [(9 * i, 15 * i, 36 * i) for i in range(8)]      # two eight-step ramps


def main():
    b = Bench("harness_renderlit.asm", org=0)
    s = b.syms
    recip = list(b.peek(s["t3d_recip"], 256))
    base = list(b.peek(s["rndl_base"], 6))
    lite = [x - 256 if x > 127 else x for x in b.peek(s["rndl_lite"], 3)]
    b.call_regs(s["demo_init"])
    b.call_regs(s["rndl_init"])

    got_ramp = list(b.peek(s["rndl_ramp"], 256))
    ramp_ok = got_ramp == rasterlit.RAMP
    print("  %-40s %s" % ("ramp table against the model",
                          "exact" if ramp_ok else "MISMATCH"))

    mod = Model()
    bad = agree = disagree = 0
    times, levels = [], set()
    frames = 400
    for f in range(frames):
        pts = mod.frame(recip)
        b.call_regs(s["demo_frame"])
        drawn_into = b.peek(s["rndl_back"], 1)[0]
        t, _ = b.call_regs(s["rndl_frame"])
        times.append(t)
        want, faces, col = rasterlit.render(pts, mod.m, mod.p, lite, base)
        levels.update(col[i] - base[i] for i in faces)
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
        for fi, idx in enumerate(raster.FACES):
            q = [pts[i] for i in idx]
            if (raster.cross(q[0], q[1], q[2]) > 0) == (fi in faces):
                agree += 1
            else:
                disagree += 1
    print("  %-40s %6d frames, %d mismatches" % ("Z80 buffer against the model",
                                                 frames, bad))
    print("  %-40s %d of %d face tests (%.2f%%)"
          % ("plane test vs screen cross product", disagree, agree + disagree,
             100.0 * disagree / (agree + disagree)))
    print("  %-40s %s" % ("shade levels used", sorted(levels)))
    print()
    print("  rndl_frame   min %d T-states, mean %.0f, max %d"
          % (min(times), sum(times) / len(times), max(times)))
    lt, _ = b.call_regs(s["rndl_light"])
    print("  rndl_light   %d T-states (one pass, all six faces)" % lt)
    dt, _ = b.call_regs(s["demo_frame"])
    print("  demo_frame   %d T-states" % dt)
    print("  together     %.0f T-states a frame, %.0f%% of a 6MHz SAM's "
          "120,000" % (sum(times) / len(times) + dt,
                       100 * (sum(times) / len(times) + dt) / 120000))
    raster.to_png(b.peek(BUF[b.peek(s["rndl_front"], 1)[0]],
                         raster.STRIDE * raster.H), "/tmp/z80lit.png", PAL)
    ok = bad == 0 and ramp_ok
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % (bad or 1)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
