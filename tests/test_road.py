#!/usr/bin/env python3
"""Verify and time road.z80s against tests/road.py.

    pip install z80
    python3 tests/test_road.py
"""
import sys

from bench import Bench
import road as A

BUF = {0x80: 0x8000, 0x20: 0x2000}


def main():
    b = Bench("harness_rd.asm", org=0)
    s = b.syms
    it, _ = b.call_regs(s["rd_init"])
    print("  rd_init   %d T-states once, sky and grass into both buffers" % it)
    # camx runs to the kerb either way, which is as far as the camera
    # can go before the road would want clipping, and then well past it
    # on both sides, which is the only thing that puts the centre on
    # the rails that stop it
    zs = (0, 2200, 9000, 14500, 21000, 30000)
    poses = [(x, z) for x in range(-A.RW, A.RW + 1, 34) for z in zs]
    poses += [(x, z) for x in (-900, -400, 400, 900) for z in zs]
    bad = 0
    times = []
    for camx, camz in poses:
        b.poke(s["rd_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["rd_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        into = b.peek(s["rd_back"], 1)[0]
        t, _ = b.call_regs(s["rd_frame"])
        times.append(t)
        want, par = A.frame(camx, camz)
        got = b.peek(BUF[into], A.STRIDE * A.H)
        rows = b.peek(s["rd_row"], 8 * (A.H - 1 - A.HZ))
        gpar = [rows[8 * (A.H - 1 - y) + 7] for y in range(A.H - 1, A.HZ, -1)]
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  PIXEL MISMATCH x=%d z=%d: %d bytes, first at %d "
                      "(y=%d x=%d) got %02X want %02X"
                      % (camx, camz, len(d), d[0], d[0] // A.STRIDE,
                         (d[0] % A.STRIDE) * 2, got[d[0]], want[d[0]]))
        if gpar != [par[y] for y in range(A.H - 1, A.HZ, -1)]:
            bad += 1
            print("  PARITY MISMATCH x=%d z=%d" % (camx, camz))
    n = len(poses)
    print("  %-40s %4d camera positions, %d mismatches"
          % ("Z80 against the model, pixels and parity", n, bad))
    print()
    dt, _ = b.call_regs(s["rd_draw"])
    mean = sum(times) / n
    print("  rd_draw      %7d T-states, %d scanlines of road"
          % (dt, A.H - 1 - A.HZ))
    print("  %-40s %7d of that is the 6,080 PUSHes"
          % ("", 11 * 64 * (A.H - 1 - A.HZ)))
    print("  rd_frame     min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %.1f%% of a 25 Hz frame, %.1f Hz"
          % ("which is", mean / 2400, 6e6 / mean))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
