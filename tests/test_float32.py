#!/usr/bin/env python3
"""Verify float32.z80s against numpy's IEEE 754 binary32 arithmetic.

Assembles the library, runs it on an emulated Z80, and compares every
result bit for bit with numpy (NaN answers are compared as "is a NaN",
since IEEE 754 does not pin down the payload).

The input space is far too large to sweep exhaustively, so the cases
are drawn from generators aimed at the places soft float goes wrong:
subnormals, exponent boundaries, near-total cancellation, operands a
few ulps apart, and sparse significands, which are what produce exact
results and exact rounding ties.

    pip install numpy z80
    python3 tests/test_float32.py [--quick]

Needs sjasmplus on PATH (or in $SJASMPLUS).
"""
import itertools
import random
import sys

import numpy as np

from bench import Bench, MASKS, check, as_f32

SIGN = 0x80000000


def edge_values():
    out = set()
    exps = (0, 1, 2, 3, 22, 125, 126, 127, 128, 129, 150, 200, 252, 253, 254, 255)
    fracs = (0, 1, 2, 3, 0x000100, 0x400000, 0x555555, 0x7FFFFD, 0x7FFFFE, 0x7FFFFF)
    for e in exps:
        for f in fracs:
            v = (e << 23) | f
            out.add(v)
            out.add(v | SIGN)
    return sorted(out)


def sparse(rng, n):
    """Values whose significand has only a few bits set.

    These multiply and divide into exact results and exact halfway
    cases far more often than uniform random bit patterns do, which is
    what exercises round-to-nearest-even.
    """
    out = []
    for _ in range(n):
        f = 0
        for _ in range(rng.randrange(1, 4)):
            f |= 1 << rng.randrange(23)
        e = rng.choice((rng.randrange(1, 255), rng.randrange(1, 8),
                        rng.randrange(120, 136), 0))
        out.append((rng.randrange(2) << 31) | (e << 23) | f)
    return out


def near_pairs(rng, n):
    """Operands a few ulps apart, in the same or opposite signs.

    This is where an adder loses its guard bits: massive cancellation
    on one side, exact ties on the other.
    """
    out = []
    for _ in range(n):
        a = rng.randrange(1 << 32)
        d = rng.choice((0, 1, 2, 3, 1 << 12, 1 << 22))
        b = (a + rng.choice((-1, 1)) * d) & 0xFFFFFFFF
        if rng.randrange(2):
            b ^= SIGN
        out.append((a, b))
    return out


def half_ulp_pairs(rng, n):
    """b sits exactly half an ulp of a below it, or one step either side.

    a + b is then an exact tie, and ties-to-even is the rule most easily
    got wrong.
    """
    out = []
    for _ in range(n):
        e = rng.randrange(25, 254)
        f = rng.randrange(1 << 23)
        a = (e << 23) | f
        b = ((e - 24) << 23) | rng.choice((0, 0, 0, 1, 0x7FFFFF))
        if rng.randrange(2):
            b ^= SIGN
        out.append((a, b))
    return out


def main():
    quick = "--quick" in sys.argv
    rng = random.Random(20260908)
    bench = Bench("harness32.asm", opsize=4)
    print("library is %d bytes (including an %d byte workspace); %s"
          % (bench.syms["f32_end"] - bench.syms["f32_sub"],
             bench.syms["f32_end"] - bench.syms["f32_ws"],
             ", ".join("%s=0x%04X" % (n, bench.syms[n])
                       for n in ("f32_add", "f32_sub", "f32_mul", "f32_div"))))

    scale = 1 if quick else 10
    edges = edge_values()
    suites = [
        ("edge cases crossed", list(itertools.product(edges, edges))),
        ("uniform random pairs",
         [(rng.randrange(1 << 32), rng.randrange(1 << 32))
          for _ in range(50000 * scale)]),
        ("sparse significands",
         list(zip(sparse(rng, 50000 * scale), sparse(rng, 50000 * scale)))),
        ("operands a few ulps apart", near_pairs(rng, 50000 * scale)),
        ("exact halfway cases", half_ulp_pairs(rng, 50000 * scale)),
        ("subnormal x anything",
         [((rng.randrange(2) << 31) | rng.randrange(1, 1 << 23),
           rng.randrange(1 << 32)) for _ in range(20000 * scale)]),
        ("anything x subnormal",
         [(rng.randrange(1 << 32),
           (rng.randrange(2) << 31) | rng.randrange(1, 1 << 23))
          for _ in range(20000 * scale)]),
    ]

    total_bad = 0
    for op in ("add", "sub", "mul", "div"):
        print("%s:" % op)
        for label, pairs in suites:
            total_bad += check(bench, op, pairs, label, width=32)

        entry = bench.syms["f32_" + op]
        sample = suites[1][1][:1500] + suites[4][1][:1500] + edges[:400]
        sample = [p if isinstance(p, tuple) else (p, p) for p in sample]
        times = [bench.fast_timed_call32(entry, a, b)[1] for a, b in sample]
        print("  %-28s min %4dT  mean %5.0fT  max %4dT"
              % ("T-states", min(times), sum(times) / len(times), max(times)))

    print("\n%s" % ("ALL TESTS PASSED" if total_bad == 0
                    else "FAILURES: %d" % total_bad))
    return 1 if total_bad else 0


if __name__ == "__main__":
    sys.exit(main())
