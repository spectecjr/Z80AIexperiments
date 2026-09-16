#!/usr/bin/env python3
"""Verify and time road2.z80s against tests/road2.py.

    pip install z80
    python3 tests/test_road2.py

road2 repaints only what moved, so a frame depends on the two before
it: this drives a whole ride rather than a list of poses, and checks
every frame of it against the ideal picture - which the routine has to
land on however little of it it chose to touch.

The bank is paged, so this runs on tests/sam.py's emulation of LMPR,
HMPR and VMPR rather than on a flat 64K, and reads a buffer back out
of physical RAM - after the flip the buffer just drawn is the one the
video hardware is displaying, and it is not mapped at all.
"""
import math
import sys

import road2 as A
from sam import Sam


def ride(n):
    """A ride: forward at 20 world units a frame, weaving kerb to kerb."""
    return [(int(0.6 * A.RW * math.sin(2 * math.pi * t / 350.0)),
             (t * 20) & 0xFFFF) for t in range(n)]


def main():
    b = Sam("harness_rd2.asm", ("harness_rd2a.asm", "harness_rd2b.asm"))
    s = b.syms
    it = b.call(s["rd2_init"])
    print("  rd2_init  %d T-states once, sky and grass into both buffers" % it)
    poses = ride(200)
    bad, times = 0, []
    for n, (camx, camz) in enumerate(poses):
        b.poke(s["rd2_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["rd2_camz"], camz.to_bytes(2, "little"))
        t = b.call(s["rd2_frame"])
        times.append(t)
        if n < 2:
            continue                    # a buffer's first frame is its init
        want, _ = A.frame(camx, camz)
        got = b.screen(b.shown())       # the flip shows what was drawn
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  FRAME %d x=%d z=%d: %d bytes, first at y=%d x=%d "
                      "got %02X want %02X"
                      % (n, camx, camz, len(d), d[0] // A.STRIDE,
                         (d[0] % A.STRIDE) * 2, got[d[0]], want[d[0]]))
    n = len(poses) - 2
    print("  %-40s %4d frames of a ride, %d wrong"
          % ("Z80 against the ideal picture", n, bad))
    print()
    t = times[2:]
    mean = sum(t) / len(t)
    print("  rd2_frame    min %7d  mean %7.0f  max %7d"
          % (min(t), mean, max(t)))
    print("  %-40s %.1f%% of a 50 Hz frame, %.1f Hz"
          % ("which is", mean / 1200, 6e6 / mean))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
