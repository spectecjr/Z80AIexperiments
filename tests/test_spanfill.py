#!/usr/bin/env python3
"""Verify and time spanfill.z80s - what a flat-shaded span costs.

    python3 tests/test_spanfill.py

The same 128 scanlines are filled with 2, 4, 6, 8, 12 and 16 spans
across, which is the range a polygonal floor would ask for, and the
line through the six timings is what a span costs and what a byte
costs. Every one of them is checked against the model first.
"""
import sys

from bench import Bench
import spanfill as S


def main():
    b = Bench("harness_span.asm", org=0)
    s = b.syms
    bad = 0
    print("  %-6s %8s %8s %8s   %s"
          % ("spans", "T-states", "a span", "of a 25Hz", "frame"))
    fit = []
    for cols in (2, 4, 6, 8, 12, 16):
        want, lst = S.frame(cols)
        b.poke(s["spn_list"], bytes(lst))
        t, _ = b.call_regs(s["spn_frame"])
        got = b.peek(0x8000, S.STRIDE * S.H)
        n = len(lst) - S.ROWS          # two bytes a span, one zero a row
        n //= 2
        if got != bytes(want):
            bad += 1
            d = [i for i in range(len(want)) if got[i] != want[i]]
            print("  MISMATCH cols=%d: %d bytes, first at %d (y=%d x=%d)"
                  % (cols, len(d), d[0], d[0] // S.STRIDE,
                     (d[0] % S.STRIDE) * 2))
        fit.append((n, t))
        print("  %-6d %8d %8.1f %7.0f%%     %d spans a scanline"
              % (cols, t, (t - S.ROWS * 92 - 128 * 128 * 5.5) / n,
                 100 * t / 240000, n // S.ROWS))
    (n0, t0), (n1, t1) = fit[0], fit[-1]
    per = (t1 - t0) / (n1 - n0)
    base = t0 - per * n0
    print()
    print("  %-46s %.1f T-states" % ("a span, off the line through the six",
                                     per))
    print("  %-46s %.1f T-states" % ("what is left for 128 scanlines of 128 "
                                     "bytes", base))
    print("  %-46s %.2f T-states" % ("which is a byte at, PUSH's floor "
                                     "being 5.5", (base - 128 * 92) / (128 * 128)))
    print("  %-46s %d" % ("frames that differed from the model", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
