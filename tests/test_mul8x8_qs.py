#!/usr/bin/env python3
"""Verify and time mul8x8_qs.z80s over every possible operand pair."""
import sys
from bench import Bench


def main():
    b = Bench("harness_qs.asm")
    e = b.syms["qsmul8"]
    bad = 0
    times = {"a>=b": [], "a<b": []}
    for a in range(256):
        for c in range(256):
            t, r = b.call_regs(e, bc=(a << 8) | c)
            if ((r >> 16) & 0xFFFF) != a * c:
                bad += 1
                if bad <= 5:
                    print("  MISMATCH %d * %d = %d" % (a, c, (r >> 16) & 0xFFFF))
            times["a>=b" if a >= c else "a<b"].append(t)
    print("  %-30s %6d cases, %d mismatches" % ("qsmul8, exhaustive", 65536, bad))
    print("  library is %d bytes: %d of code, 1024 of tables"
          % (b.syms["qs_end"] - b.syms["qsmul8"],
             b.syms["qs_f"] - b.syms["qsmul8"]))
    for k in ("a>=b", "a<b"):
        ts = times[k]
        print("  qsmul8, %-5s  min %3dT  mean %5.1fT  max %3dT"
              % (k, min(ts), sum(ts) / len(ts), max(ts)))
    every = times["a>=b"] + times["a<b"]
    print("  qsmul8, overall  mean %5.1fT   (mult8x8_16 is 156.5T)"
          % (sum(every) / len(every)))
    print("\n%s" % ("ALL TESTS PASSED" if bad == 0 else "FAILURES: %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
