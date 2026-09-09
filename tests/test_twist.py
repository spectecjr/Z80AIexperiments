#!/usr/bin/env python3
"""Verify and time twist.z80s against tests/twist.py.

    pip install z80
    python3 tests/test_twist.py
"""
import sys

from bench import Bench
import twist as T

BUF = {0x80: 0x8000, 0x20: 0x2000}


def main():
    b = Bench("harness_twist.asm", org=0)
    s = b.syms
    it, _ = b.call_regs(s["tw_init"])
    print("  tw_init   %d T-states once, the backdrop into both buffers" % it)
    bad = 0
    times = []
    for base in range(0, 256, 11):
        for delta in (1, 3, 7):
            b.poke(s["tw_ang"], bytes([base]))
            b.poke(s["tw_delta"], bytes([delta]))
            into = b.peek(s["tw_back"], 1)[0]
            t, _ = b.call_regs(s["tw_frame"])
            times.append(t)
            want = T.frame(base, delta)
            got = b.peek(BUF[into], T.STRIDE * T.H)
            band = [i for i in range(len(want))
                    if got[i] != want[i]
                    and T.BX <= i % T.STRIDE < T.BX + T.BW]
            if band:
                bad += 1
                if bad <= 3:
                    i = band[0]
                    print("  MISMATCH base %d delta %d: %d bytes, first at "
                          "y=%d byte=%d got %02X want %02X"
                          % (base, delta, len(band), i // T.STRIDE,
                             i % T.STRIDE, got[i], want[i]))
    n = len(times)
    mean = sum(times) / n
    print("  %-40s %4d angles, %d mismatches" % ("Z80 against the model",
                                                 n, bad))
    print()
    dt, _ = b.call_regs(s["tw_draw"])
    print("  tw_draw      %7d T-states, 192 scanlines" % dt)
    print("  tw_frame     min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %.1f%% of a 50 Hz frame" % ("which is", mean / 1200))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
