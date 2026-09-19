#!/usr/bin/env python3
"""
profile.py - measure what the prototype actually costs, by running it.

Every memory access the Z80 makes goes through the SAM bus in bubble/tools/sam.py,
and on a SAM one memory access is exactly one contention slot. So counting
bus traffic per frame, attributed to the nearest label, gives the real
per-routine cost in the only currency that matters on this machine.

This exists because the hand-built cost model in docs/BUBBLE_BOBBLE_SAM.md
was wrong by 4.6x on its single largest item, and nothing but measurement
would have caught it.

Run: python3 bubble/tools/profile.py [frames] [warmup]
"""

import bisect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from collections import Counter                                # noqa: E402
from sam import Machine                                        # noqa: E402

IMAGE = os.path.join(HERE, "..", "build", "bb.bin")
SYMS = os.path.join(HERE, "..", "build", "bb.sym")
FRAME_BUDGET = 23808
OBJ_TABLE = 0x5C00
OBJ_MAX, OBJ_SIZE = 48, 16


def load_symbols():
    out = []
    for line in open(SYMS):
        p = line.split()
        if len(p) >= 3 and p[1].upper() == "EQU" and p[0].startswith("bb_"):
            a = int(p[2].rstrip("Hh"), 16)
            if a < 0x5000:                     # code and compiled sprites
                out.append((a, p[0]))
    out.sort()
    return [a for a, _ in out], [n for _, n in out]


def main():
    frames = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    warmup = int(sys.argv[2]) if len(sys.argv) > 2 else 190

    addrs, names = load_symbols()

    def near(a):
        i = bisect.bisect_right(addrs, a) - 1
        return names[i] if i >= 0 else "?"

    m = Machine(open(IMAGE, "rb").read())
    m.boot()
    cpu, s = m.cpu, m.sam
    orb, owb = s.rb, s.wb
    tally = Counter()
    on = [False]

    def rb(a):
        if on[0]:
            tally[near(cpu.pc)] += 1
        return orb(a)

    def wb(a, v):
        if on[0]:
            tally[near(cpu.pc)] += 1
        owb(a, v)

    s.rb, s.wb = rb, wb

    live = 0
    for f in range(warmup + frames):
        on[0] = f >= warmup
        if f == warmup:
            tally.clear()
        m.run_frame()
        if on[0]:
            live += sum(1 for i in range(OBJ_MAX)
                        if orb(OBJ_TABLE + i * OBJ_SIZE))

    total = sum(tally.values())
    print("measured over %d frames, %.1f live objects on average"
          % (frames, live / frames))
    print("  frame budget      %6d accesses" % FRAME_BUDGET)
    print("  measured mean     %6d accesses   %.2fx over budget"
          % (total / frames, total / frames / FRAME_BUDGET))
    print()
    print("  %-24s %9s  %s" % ("nearest label", "a/frame", "share"))
    for k, v in tally.most_common(15):
        print("  %-24s %9d  %5.1f%%" % (k, v / frames, 100.0 * v / total))


if __name__ == "__main__":
    main()
