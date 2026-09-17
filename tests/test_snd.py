#!/usr/bin/env python3
"""Measure the 50 Hz tick that has to happen inside a 25 Hz frame.

    pip install z80
    python3 tests/test_snd.py

A SAA1099 wants feeding fifty times a second and these demos draw
twenty-five times a second with interrupts off throughout, so one of
the two ticks a frame lands in the middle of the drawing. snd.z80s
schedules it rather than polling for it: the caller knows what every
band of the board costs, so it knows which band the second tick belongs
in, and pokes the number.

What this measures is the two halves of that - what the question costs
at every band, and what the answer costs when it is yes - against the
frame it has to fit inside. sound.md is the design note.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sam import Sam                                     # noqa: E402

BANDS = (19, 80)                # a board is 19 bands at the shallowest
                                # horizon and 80 at the deepest
LOG = "harness_sndlog.asm"


def main():
    b = Sam("harness_snd.asm", (LOG,), screens=(10, 12))
    s = b.syms
    b.report_memory()
    b.poke(s["snd_at"], s["snd_log"].to_bytes(2, "little"))

    # The bench calls the point, so what it measures carries a RET the
    # inline version does not have - and on the firing path a RET and the
    # stack pointer the bench wants back as well.
    MISS, FIRE = 10, 40
    miss = []                   # the question, at a band that is not it
    for _ in range(4):
        b.poke(s["snd_n"], bytes([200]))
        miss.append(b.call(s["snd_point"]) - MISS)
    print("  %-40s %4d T-states, and a board is %d bands to %d"
          % ("the check, at a band that is not it", min(miss), *BANDS))
    print("  %-40s %4d … %d T-states a frame"
          % ("  so the board pays", min(miss) * BANDS[0],
             min(miss) * BANDS[1]))

    ticks = []                  # and the tick itself, over the log
    for _ in range(400):
        b.poke(s["snd_n"], bytes([1]))
        b.poke(s["snd_sp"], (0x7FF0).to_bytes(2, "little"))
        ticks.append(b.call(s["snd_point"]) - FIRE)
    ticks.sort()
    print("  %-40s %4d T-states, nothing to say that frame"
          % ("a tick, the point and the player", ticks[0]))
    print("  %-40s %4d T-states, its median frame" % ("", ticks[len(ticks) // 2]))
    print("  %-40s %4d T-states, its worst (31 pairs)" % ("", ticks[-1]))
    print("  %-40s %4d T-states a pair, against saa.z80s's 74"
          % ("which is", round((ticks[-1] - ticks[0]) / 31)))

    print()
    worst = min(miss) * BANDS[1] + 2 * ticks[-1]
    mean = min(miss) * 50 + 2 * (sum(ticks) // len(ticks))
    print("  %-40s %5d T-states a frame" % ("sound, worst case", worst))
    print("  %-40s %5d T-states a frame" % ("sound, mean", mean))
    print("  %-40s %5.1f%% of a 25 Hz frame, and chequer10's"
          % ("which is", 100 * worst / 240000))
    print("  %-40s %5.1f%% at its worst frame"
          % ("worst frame goes to", 100 * (222452 + worst) / 240000))

    ok = ticks[0] > 0 and min(miss) > 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
