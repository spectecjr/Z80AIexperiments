#!/usr/bin/env python3
"""Cycle costs of the float16.z80s routines, measured on an emulated Z80.

Counts T-states from the first instruction of a routine to its RET
inclusive; a caller pays that plus 17T for its own CALL. Reports the
range and the mean over three populations: every operand pair (uniform
over the 32-bit input space), pairs of finite nonzero operands (what
real arithmetic actually costs), and the special-case exits.

    python3 tests/timing.py [nrandom]
"""
import random
import sys

from bench import Bench, OPS, as_f16

PROBES = 32             # fixed partners crossed with all 65536 operands


def classify(a, b):
    special = ((a & 0x7C00) == 0x7C00 or (b & 0x7C00) == 0x7C00
               or (a & 0x7FFF) == 0 or (b & 0x7FFF) == 0)
    return "special" if special else "finite"


def main():
    nrandom = int(sys.argv[1]) if len(sys.argv) > 1 else 1000000
    random.seed(20260908)
    bench = Bench()

    # a spread of probe values: one per exponent, both signs, plus the
    # values known to drive the slow paths
    probes = [(e << 10) | f for e in range(0, 32, 4) for f in (0, 0x155, 0x3FF)]
    probes += [0x0000, 0x8000, 0x0001, 0x8001, 0x03FF, 0x0400, 0x3C00,
               0xBC00, 0x7BFF, 0x7C00, 0x7E00]
    probes = sorted(set(probes))[:PROBES]

    pairs = []
    for probe in probes:
        pairs += [(a, probe) for a in range(65536)]
        pairs += [(probe, b) for b in range(65536)]
    pairs += [(random.randrange(65536), random.randrange(65536))
              for _ in range(nrandom)]

    print("%d timed calls per operation (%d probes x 2 x 65536, plus %d "
          "random pairs)\n" % (len(pairs), len(probes), nrandom))
    print("%-5s %28s %28s   %s"
          % ("", "all operand pairs", "finite operands only", "special-case exits"))
    print("%-5s %8s %8s %8s  %8s %8s %8s  %6s %6s"
          % ("op", "min", "mean", "max", "min", "mean", "max", "min", "max"))

    for op in ("add", "sub", "mul", "div"):
        entry = bench.syms[OPS[op][0]]
        groups = {"finite": [], "special": []}
        worst = (0, None)
        for a, b in pairs:
            t = bench.fast_timed_call(entry, a, b)[1]
            groups[classify(a, b)].append(t)
            if t > worst[0]:
                worst = (t, (a, b))
        every = groups["finite"] + groups["special"]
        fin, spc = groups["finite"], groups["special"]
        print("%-5s %8d %8.0f %8d  %8d %8.0f %8d  %6d %6d"
              % (op, min(every), sum(every) / len(every), max(every),
                 min(fin), sum(fin) / len(fin), max(fin),
                 min(spc), max(spc)))
        print("      worst case %dT at %r %s %r"
              % (worst[0], as_f16(worst[1][0]), op, as_f16(worst[1][1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
