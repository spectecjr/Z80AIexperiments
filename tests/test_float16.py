#!/usr/bin/env python3
"""Verify float16.z80s against numpy's IEEE 754 binary16 arithmetic.

Assembles the library, runs it on an emulated Z80, and compares every
result bit for bit with numpy (NaN answers are compared as "is a NaN",
since IEEE 754 does not pin down the payload).

    pip install numpy z80
    python3 tests/test_float16.py [--quick]

Needs sjasmplus on PATH (or in $SJASMPLUS).
"""
import itertools
import random
import sys

from bench import Bench, OPS, check, as_f16

# Values worth crossing with everything: zeros, the smallest and
# largest subnormals, the subnormal/normal boundary, one-ulp steps
# either side of 1.0, the largest finite, infinities and NaNs.
INTERESTING = [
    0x0000, 0x8000,                 # +-0
    0x0001, 0x8001,                 # +-smallest subnormal
    0x03FF, 0x83FF,                 # +-largest subnormal
    0x0400, 0x8400,                 # +-smallest normal
    0x3C00, 0xBC00,                 # +-1
    0x3C01, 0x3BFF,                 # 1+ulp, 1-ulp
    0x4200, 0xC200,                 # +-3
    0x7BFF, 0xFBFF,                 # +-65504, the largest finite
    0x7C00, 0xFC00,                 # +-Inf
    0x7E00, 0x7C01, 0xFFFF,         # NaNs
]


def edge_values():
    """A value from every exponent, at several places in the binade."""
    out = set(INTERESTING)
    for e in range(32):
        for f in (0x000, 0x001, 0x002, 0x1FF, 0x200, 0x3FE, 0x3FF):
            out.add((e << 10) | f)
            out.add(0x8000 | (e << 10) | f)
    return sorted(out)


def main():
    quick = "--quick" in sys.argv
    random.seed(20260908)
    bench = Bench()
    edges = edge_values()
    print("library is %d bytes; %s"
          % (bench.syms["f16_end"] - bench.syms["f16_sub"],
             ", ".join("%s=0x%04X" % (n, bench.syms[n])
                       for n in ("f16_add", "f16_sub", "f16_mul", "f16_div"))))

    nrandom = 100000 if quick else 2000000
    probes = INTERESTING if quick else edges[::7] + INTERESTING

    total_bad = 0
    for op in ("add", "sub", "mul", "div"):
        print("%s:" % op)

        # every possible operand against a handful of fixed partners,
        # on both sides - this alone covers the whole 16-bit input
        # space for one operand
        pairs = []
        for probe in probes:
            pairs += [(a, probe) for a in range(65536)]
            pairs += [(probe, b) for b in range(65536)]
        total_bad += check(bench, op, pairs, "exhaustive x %d probes" % len(probes))

        # all the awkward values against each other
        pairs = list(itertools.product(edges, edges))
        total_bad += check(bench, op, pairs, "edge cases crossed")

        # and a large uniform random sample
        pairs = [(random.randrange(65536), random.randrange(65536))
                 for _ in range(nrandom)]
        total_bad += check(bench, op, pairs, "random pairs")

        # a rough timing sample; tests/timing.py does this properly
        entry = bench.syms[OPS[op][0]]
        sample = [(random.randrange(65536), random.randrange(65536))
                  for _ in range(2000)] + list(itertools.product(INTERESTING,
                                                                INTERESTING))
        times = [bench.fast_timed_call(entry, a, b)[1] for a, b in sample]
        worst = max(range(len(times)), key=lambda i: times[i])
        print("  %-28s min %4dT  mean %5.0fT  max %4dT  (worst: %r %s %r)"
              % ("T-states", min(times), sum(times) / len(times), max(times),
                 as_f16(sample[worst][0]), op, as_f16(sample[worst][1])))

    print("\n%s" % ("ALL TESTS PASSED" if total_bad == 0
                    else "FAILURES: %d" % total_bad))
    return 1 if total_bad else 0


if __name__ == "__main__":
    sys.exit(main())
