#!/usr/bin/env python3
"""Verify and time chequer6 - chequer5's board with a pilot over it.

    pip install z80
    python3 tests/test_chequer6.py

The board is chequer5's, paged bank and all. What is checked here is the
pilot: three poses, each drawn over the board in both halves, with the
bytes where only one of its two pixels is covered keeping the board's
other pixel.

The top half of a pose is drawn once per buffer, so a pose change takes
two frames to appear everywhere - which the sweep below drives on
purpose, a pose at a time, checking every frame.
"""
import os
import sys

os.environ["HARRIER_MINP"] = "1"        # before the model reads the geometry

import chequer6 as C
from sam import Sam

CHUNKS = ("harness_chq5c0.asm", "harness_chq5c1.asm",   # the board's bank,
          "harness_chq5c2.asm",                         # cut by band
          "harness_chq5msk0.asm", "harness_chq5msk1.asm")


def main():
    b = Sam("harness_chq6.asm", CHUNKS, screens=(10, 12),
            chunk_defines=lambda y: {"CHQ4_RET": y["chq4_ret"]})
    s = b.syms
    b.report_memory()
    it = b.call(s["chq6_init"])
    print("  chq6_init %d T-states once, the sky into both buffers" % it)
    # camx runs past one square and goes negative, because the square
    # the camera is standing in is a parity of its own
    poses = [(x, z, (i // 7) % 3)
             for i, (x, z) in enumerate((x, z)
                                        for x in range(-640, 641, 47)
                                        for z in (0, 100, 900, 4321))]
    bad = 0
    times = []
    for camx, camz, pose in poses:
        b.poke(s["chq4_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq4_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq6_pose"], bytes([pose]))
        t = b.call(s["chq6_frame"])
        times.append(t)
        want = C.frame(camx, camz, pose)
        got = b.screen(b.shown())
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  PIXEL MISMATCH x=%d z=%d pose=%d: %d bytes, first "
                      "at %d (y=%d x=%d p=%d) got %02X want %02X"
                      % (camx, camz, pose, len(d), d[0], d[0] // C.STRIDE,
                         (d[0] % C.STRIDE) * 2, C.PTAB[d[0] // C.STRIDE],
                         got[d[0]], want[d[0]]))
    n = len(poses)
    print("  %-40s %4d camera positions, %d mismatches"
          % ("Z80 against the model, pixels", n, bad))
    print("  %-40s %d, the narrowest square drawn"
          % ("squares as small as", min(p for p in C.PTAB if p)))
    print()
    ft = b.call(s["chq4_floor"])
    mt = b.call(s["chq4_msk8"])
    b.call(s["chq6_frame"])             # the pose is settled in both
    b.call(s["chq6_frame"])             # buffers by the second of these
    pt = b.call(s["chq6_frame"])
    mean = sum(times) / n
    print("  chq4_floor   %7d T-states, %d scanlines of board"
          % (ft, 192 - C.TOP))
    print("  chq4_msk8    %7d T-states, the swap mask a scanline" % mt)
    print("  the pilot    %7d T-states, 47 rows of it a frame"
          % (pt - ft - mt))
    print("  chq6_frame   min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %.1f%% of a 50 Hz frame, %.1f Hz free running,"
          % ("which is", mean / 1200, 6e6 / mean))
    print("  %-40s %d Hz against the display"
          % ("", 50 // max(1, -(-int(mean) // 120000))))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
