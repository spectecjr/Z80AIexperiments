#!/usr/bin/env python3
"""Cycle costs of the float16.z80s and float32.z80s routines.

Counts T-states from the first instruction of a routine to its RET
inclusive; a caller pays that plus 17T for its own CALL. Reports the
range and the mean over two populations: pairs of finite nonzero
operands (what real arithmetic costs) and the special-case exits.

    python3 tests/timing.py [16|32] [nrandom]

For binary16 every value of each operand is tried against a set of
probes, so the range is close to exact. For binary32 the space is far
too large for that, and the cases come from the same generators the
correctness tests use.
"""
import random
import sys

from bench import Bench, OPS, as_float

PROBES = 32


def f16_pairs(rng, nrandom):
    probes = [(e << 10) | f for e in range(0, 32, 4) for f in (0, 0x155, 0x3FF)]
    probes += [0x0000, 0x8000, 0x0001, 0x8001, 0x03FF, 0x0400, 0x3C00,
               0xBC00, 0x7BFF, 0x7C00, 0x7E00]
    probes = sorted(set(probes))[:PROBES]
    pairs = []
    for probe in probes:
        pairs += [(a, probe) for a in range(65536)]
        pairs += [(probe, b) for b in range(65536)]
    pairs += [(rng.randrange(65536), rng.randrange(65536))
              for _ in range(nrandom)]
    return pairs, "%d probes x 2 x 65536, plus %d random pairs" % (len(probes),
                                                                   nrandom)


def f32_pairs(rng, nrandom):
    import test_float32 as t32
    edges = t32.edge_values()
    n = max(nrandom // 5, 1)
    pairs = [(rng.choice(edges), rng.choice(edges)) for _ in range(n)]
    pairs += [(rng.randrange(1 << 32), rng.randrange(1 << 32)) for _ in range(n)]
    pairs += list(zip(t32.sparse(rng, n), t32.sparse(rng, n)))
    pairs += t32.near_pairs(rng, n)
    pairs += t32.half_ulp_pairs(rng, n)
    return pairs, "edge, uniform, sparse, near and halfway cases"


def main():
    width = 16
    args = [a for a in sys.argv[1:]]
    if args and args[0] in ("16", "32"):
        width = int(args.pop(0))
    nrandom = int(args[0]) if args else (1000000 if width == 16 else 400000)
    rng = random.Random(20260908)

    if width == 16:
        bench = Bench()
        pairs, how = f16_pairs(rng, nrandom)
        call = bench.fast_timed_call
        expmask, zeromask = 0x7C00, 0x7FFF
    else:
        bench = Bench("harness32.asm", opsize=4)
        pairs, how = f32_pairs(rng, nrandom)
        call = bench.fast_timed_call32
        expmask, zeromask = 0x7F800000, 0x7FFFFFFF

    print("binary%d: %d timed calls per operation (%s)\n"
          % (width, len(pairs), how))
    print("%-5s %26s %20s" % ("", "finite operands", "zero/Inf/NaN operand"))
    print("%-5s %8s %8s %8s  %8s %8s" % ("op", "min", "mean", "max",
                                         "min", "max"))

    for op in ("add", "sub", "mul", "div"):
        entry = bench.syms["f%d_%s" % (width, op)]
        fin, spc = [], []
        worst = (0, None)
        for a, b in pairs:
            t = call(entry, a, b)[1]
            special = ((a & expmask) == expmask or (b & expmask) == expmask
                       or (a & zeromask) == 0 or (b & zeromask) == 0)
            (spc if special else fin).append(t)
            if t > worst[0]:
                worst = (t, (a, b))
        print("%-5s %8d %8.0f %8d  %8d %8d"
              % (op, min(fin), sum(fin) / len(fin), max(fin),
                 min(spc), max(spc)))
        print("      worst case %dT at %r %s %r"
              % (worst[0], as_float(worst[1][0], width), op,
                 as_float(worst[1][1], width)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
