#!/usr/bin/env python3
"""Verify and time roto.z80s against tests/roto.py.

    pip install z80
    python3 tests/test_roto.py
"""
import math
import sys

from bench import Bench
import roto as R

BUF = {0x80: 0x8000, 0x20: 0x2000}


def main():
    b = Bench("harness_roto.asm", org=0)
    s = b.syms
    b.call_regs(s["rz_init"])
    tex = list(b.peek(s["rz_tex"], 256))
    bad = 0
    times = []
    for k in range(12):
        ang = 2 * math.pi * k / 12
        z = 0.6 + 0.5 * math.sin(ang * 2)
        du = int(-256 * z * math.cos(ang)) & 0xFFFF
        dv = int(256 * z * math.sin(ang)) & 0xFFFF
        dux = int(256 * z * math.sin(ang)) & 0xFFFF
        dvx = int(256 * z * math.cos(ang)) & 0xFFFF
        ur, vr = (k * 313) & 0xFFFF, (k * 517) & 0xFFFF
        for n, v in (("rz_ur", ur), ("rz_vr", vr), ("rz_du", du),
                     ("rz_dv", dv), ("rz_dux", dux), ("rz_dvx", dvx)):
            b.poke(s[n], v.to_bytes(2, "little"))
        into = b.peek(s["rz_back"], 1)[0]
        t, _ = b.call_regs(s["rz_frame"])
        times.append(t)
        want = R.frame(ur, vr, du, dv, dux, dvx, tex)
        got = b.peek(BUF[into], R.STRIDE * R.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  MISMATCH %d: %d bytes, first at y=%d byte=%d "
                      "got %02X want %02X"
                      % (k, len(d), d[0] // R.STRIDE, d[0] % R.STRIDE,
                         got[d[0]], want[d[0]]))
    n = len(times)
    mean = sum(times) / n
    px = R.BW * R.BH
    print("  %-40s %4d angles, %d mismatches"
          % ("Z80 against the model", n, bad))
    print()
    print("  rz_frame     min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %.1f T-states a byte" % ("for %d bytes, that is" % px,
                                            mean / px))
    print("  %-40s %.1f Hz" % ("which at 6 MHz is", 6e6 / mean))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
