#!/usr/bin/env python3
"""Verify and time harrier.z80s against tests/harrier.py.

    pip install z80
    python3 tests/test_harrier.py
"""
import sys

from bench import Bench
import harrier as A

BUF = {0x80: 0x8000, 0x20: 0x2000}


def main():
    b = Bench("harness_hr.asm", org=0)
    s = b.syms
    it, _ = b.call_regs(s["hr_init"])
    print("  hr_init   %d T-states once, sky and haze into both buffers" % it)
    poses = [(x, z) for x in range(0, 256, 37) for z in (0, 100, 900, 4321)]
    bad = 0
    times = []
    for camx, camz in poses:
        b.poke(s["hr_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["hr_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        into = b.peek(s["hr_back"], 1)[0]
        t, _ = b.call_regs(s["hr_frame"])
        times.append(t)
        want, par = A.frame(camx, camz)
        got = b.peek(BUF[into], A.STRIDE * A.H)
        gpar = b.peek(s["hr_par"], A.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  PIXEL MISMATCH x=%d z=%d: %d bytes, first at %d "
                      "(y=%d x=%d) got %02X want %02X"
                      % (camx, camz, len(d), d[0], d[0] // A.STRIDE,
                         (d[0] % A.STRIDE) * 2, got[d[0]], want[d[0]]))
        if list(gpar[A.HZ + 1:]) != par[A.HZ + 1:]:
            bad += 1
            print("  PARITY MISMATCH x=%d z=%d" % (camx, camz))
    n = len(poses)
    print("  %-40s %4d camera positions, %d mismatches"
          % ("Z80 against the model, pixels and parity", n, bad))
    print()
    dt, _ = b.call_regs(s["hr_draw"])
    pt, _ = b.call_regs(s["hr_par8"])
    mean = sum(times) / n
    print("  hr_draw      %7d T-states, %d scanlines of board"
          % (dt, 192 - A.TOP))
    print("  hr_par8      %7d T-states, the palette parities" % pt)
    print("  hr_frame     min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %.1f%% of a 25 Hz frame, %.1f Hz"
          % ("which is", mean / 2400, 6e6 / mean))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
