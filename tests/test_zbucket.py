#!/usr/bin/env python3
"""Six sprite variants and a z-bucket, instead of a scale per sprite.

    python3 tests/test_zbucket.py

The other way round from `test_mipsprite.py`: there the width is
quantised and the height is free, so a sprite is scaled to its own z.
Here nothing is scaled at run time at all. Six variants exist, a sprite
is snapped to whichever one its z falls in, and the only thing that
changes between frames is which variant gets called.

That buys the `whole` shape everywhere - no row program, no dispatcher -
and costs a step in apparent size at every bucket boundary. What is
measured here is what the step costs, because it is not free either:
when a sprite drops a bucket the box it leaves behind is bigger than the
one that replaces it, and the ring between them has to be cleared in
both buffers.

Everything is checked against the model before it is timed, the same way.
"""
import sys

import mipsprite as M
from test_mipsprite import Box, Bench, build_whole, measure, CODE


FRAME = 120000


def scaled_motion(lv, top):
    """A sprite 3x further away crosses 3x fewer pixels a frame."""
    dx = max(1, round(4 * lv.wb / top.wb))
    dy = max(1, round(8 * lv.hpx / top.hpx))
    return dx, dy


def main():
    ch = M.chain(widths=M.BUCKETS)
    b = Bench()
    bad = [0]

    def run(lv, h, kind, **kw):
        t, size, e = measure(b, lv, h, kind, **kw)
        bad[0] += e
        return t, size

    def erase(wb, h):
        if wb <= 0 or h <= 0:
            return 0
        t, _ = run(Box(wb, h), h, "erase", wevery=4)
        return t

    print("Six variants on a z-bucket. 6 MHz SAM, MODE 4, 120,000 T-states")
    print("between 50 Hz interrupts. Opaque box, whole, a window every")
    print("fourth row - no row program and no dispatcher anywhere.\n")

    print("  %-3s %-8s %6s %6s %9s %8s %8s %8s"
          % ("z", "size", "box", "drawn", "T-states", "T/byte", "% frame",
             "code"))
    draws = []
    for k, lv in enumerate(ch):
        t, size = run(lv.opaque(), lv.hpx, "whole", wevery=4)
        draws.append(t)
        print("  %-3d %-8s %6d %6d %9d %8.1f %7.1f%% %8d"
              % (k, "%dx%d" % (lv.wpx, lv.hpx), lv.wb * lv.hpx, lv.area,
                 t, t / (lv.wb * lv.hpx), 100.0 * t / FRAME, size))

    print("\n  Holding still in a bucket: the draw, plus the L the sprite")
    print("  leaves as it moves (scaled with the bucket, 4 bytes and 8 rows")
    print("  a frame at the top).\n")
    print("  %-3s %-8s %9s %8s %9s %8s %9s"
          % ("z", "size", "draw", "the L", "a frame", "% frame", "how many"))
    steady = []
    for k, lv in enumerate(ch):
        dx, dy = scaled_motion(lv, ch[0])
        l = erase(dx, lv.hpx) + erase(lv.wb - dx, dy)
        steady.append(draws[k] + l)
        print("  %-3d %-8s %9d %8d %9d %7.1f%% %9.1f"
              % (k, "%dx%d" % (lv.wpx, lv.hpx), draws[k], l, steady[k],
                 100.0 * steady[k] / FRAME, FRAME / steady[k]))

    print("\n  Crossing a boundary. Growing costs nothing - the bigger box")
    print("  swallows the smaller one. Shrinking leaves a ring, and with")
    print("  two buffers the ring has to be cleared in both, so it is paid")
    print("  on the crossing frame and the one after it.\n")
    print("  %-14s %7s %9s %9s %9s %8s"
          % ("boundary", "ring", "clear it", "and draw", "of steady",
             "% frame"))
    for k in range(len(ch) - 1):
        a, c = ch[k], ch[k + 1]
        dw, dh = a.wb - c.wb, a.hpx - c.hpx
        ring = (erase(a.wb, (dh + 1) // 2) + erase(a.wb, dh // 2)
                + erase((dw + 1) // 2, c.hpx) + erase(dw // 2, c.hpx))
        area = a.wb * a.hpx - c.wb * c.hpx
        both = ring + draws[k + 1]
        print("  %-14s %7d %9d %9d %8.1fx %7.1f%%"
              % ("%dx%d -> %dx%d" % (a.wpx, a.hpx, c.wpx, c.hpx), area,
                 ring, both, both / steady[k + 1], 100.0 * both / FRAME))

    print("\n  The other way to cross: draw the smaller picture inside the")
    print("  box it is leaving for those two frames, so there is no ring at")
    print("  all - one extra compiled form a boundary.\n")
    print("  %-14s %9s %9s %9s %8s"
          % ("boundary", "ring+draw", "padded", "saved", "code"))
    for k in range(len(ch) - 1):
        a, c = ch[k], ch[k + 1]
        dw, dh = a.wb - c.wb, a.hpx - c.hpx
        ring = (erase(a.wb, (dh + 1) // 2) + erase(a.wb, dh // 2)
                + erase((dw + 1) // 2, c.hpx) + erase(dw // 2, c.hpx))
        pad = c.padded(a.wb, a.hpx)
        t, size = run(pad, a.hpx, "whole", wevery=4)
        print("  %-14s %9d %9d %9d %8d"
              % ("%dx%d -> %dx%d" % (a.wpx, a.hpx, c.wpx, c.hpx),
                 ring + draws[k + 1], t, ring + draws[k + 1] - t, size))

    print("\n  What the bucket costs in memory and in per-sprite work:")
    code = sum(len(build_whole(lv.opaque(), CODE, lv.hpx)[0].b) for lv in ch)
    cont = sum(len(build_whole(lv.opaque(), CODE, lv.hpx)[0].b)
               for lv in M.chain())
    print("    %-44s %6d bytes" % ("six variants, opaque, whole", code))
    print("    %-44s %6d" % ("the seven-level chain, same shape", cont))
    print("    %-44s %6d" % ("a row program a level, which is now gone", 0))

    print("\n  A scene of fifteen, spread over the six buckets:")
    tot = 0
    for k, n in ((0, 1), (1, 1), (2, 2), (3, 3), (4, 4), (5, 4)):
        tot += n * steady[k]
        print("    %-2d x %-8s %9d %7.1f%%"
              % (n, "%dx%d" % (ch[k].wpx, ch[k].hpx), n * steady[k],
                 100.0 * n * steady[k] / FRAME))
    print("    %-13s %9d %7.1f%%" % ("fifteen", tot, 100.0 * tot / FRAME))

    print("\n  %-46s %d" % ("screen bytes that differed from the model",
                            bad[0]))
    ok = bad[0] == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad[0]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
