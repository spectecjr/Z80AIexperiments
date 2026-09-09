#!/usr/bin/env python3
"""Verify and time portal.z80s against tests/portal.py.

Walks a camera round the maze, comparing every drawn byte with the
model and counting what a frame costs. The model is room.py's
arithmetic driven through doors, so a mismatch here is either the
recursion or the window, not the trapezoid raster - test_room3d.py
covers that.

    pip install z80
    python3 tests/test_portal.py
"""
import math
import sys

from bench import Bench
import portal as P
import room as R
from test_room3d import PAL

BUF = {0x80: 0x8000, 0x20: 0x2000}


CENTRES = [(-320, -320), (0, -320), (320, -320), (320, 0),
           (320, 320), (0, 320), (-320, 320), (-320, 0)]


def path(t, n=256):
    """A lap of the ring corridor, looking around between the doors.

    Two things this walk does that a walk in this maze has to: it goes
    through a door rather than standing in one, and it looks straight
    ahead while it does - see p_here in portal.z80s and the invariants
    in portal.md.
    """
    u = 8.0 * t / n
    i, f = int(u) % 8, u - int(u)
    x0, z0 = CENTRES[i]
    x1, z1 = CENTRES[(i + 1) % 8]
    x = int(round(x0 + (x1 - x0) * f))
    z = int(round(z0 + (z1 - z0) * f))
    ca = int(round(math.atan2(x1 - x0, z1 - z0) * 128 / math.pi)) & 255
    d = min(min(abs(x - b) for b in (P.XS[1], P.XS[2])),
            min(abs(z - b) for b in (P.ZS[1], P.ZS[2])))
    look = 40 * min(1.0, d / 96.0) * math.sin(2 * math.pi * t / 64)
    return x, z, (ca + int(look)) & 255


def main():
    b = Bench("harness_portal.asm", org=0)
    s = b.syms
    b.call_regs(s["p_init"])
    ceil_col = b.peek(s["r3d_scc"], 1)[0] & 15
    floor_col = b.peek(s["r3d_sfc"], 1)[0] & 15
    print("  maze %d vertices, %d sectors, %d walls"
          % (len(P.VERTS), len(P.SECTORS), sum(len(w) for w in P.SECTORS)))

    bad, times, strips, shown = 0, [], [], None
    frames = 256
    for f in range(frames):
        cx, cz, ca = path(f)
        here = P.sector_for((cx, cz, ca))
        b.poke(s["r3d_cx"], (cx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_cz"], (cz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_ca"], bytes([ca]))
        b.poke(s["p_here"], bytes([here]))
        into = b.peek(s["r3d_back"], 1)[0]
        t, _ = b.call_regs(s["p_frame"])
        times.append(t)
        want, st = P.render((cx, cz, ca), ceil_col, floor_col, sector=here)
        strips.append(len(st))
        got = b.peek(BUF[into], R.STRIDE * R.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  MISMATCH frame %d cam %s sector %d: %d bytes, first "
                      "at %d (y=%d x=%d) got %02X want %02X"
                      % (f, (cx, cz, ca), here, len(d), d[0],
                         d[0] // R.STRIDE, (d[0] % R.STRIDE) * 2,
                         got[d[0]], want[d[0]]))
                print("     strips %s" % (st,))
        elif shown is None and len(st) >= 5:
            shown = got
    n = len(times)
    print("  %-40s %6d frames, %d mismatches"
          % ("Z80 buffer against the model", frames, bad))
    print("  %-40s min %d, mean %.2f, max %d"
          % ("walls drawn a frame", min(strips), sum(strips) / n, max(strips)))
    print()
    print("  p_frame      min %d T-states, mean %.0f, max %d"
          % (min(times), sum(times) / n, max(times)))
    print("  %-40s %.0f%% of 240,000 (25 Hz on a 6 MHz SAM)"
          % ("mean", 100 * (sum(times) / n) / 240000))
    print("  %-40s %.1f Hz mean, %.1f Hz worst"
          % ("which at 6 MHz is", 6e6 / (sum(times) / n), 6e6 / max(times)))
    if shown is not None:
        import raster
        raster.to_png(shown, "/tmp/z80portal.png", PAL)
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
