#!/usr/bin/env python3
"""Verify and time chequer7 - the board, a city, and a pilot over both.

    pip install z80
    python3 tests/test_chequer7.py

The board and the pilot are chequer6's. What is checked here is the
city: sixteen scanlines of two skylines scrolling at different speeds,
redrawn whole every frame, with the pilot drawn over the top of them
and the pilot's own division moved up to the city's first row.

The sweep drives the city's clock through a whole period of the far
layer, which is a whole two periods of the near one, so every wrap of
every building is checked - including the odd byte a wrap leaves when
the far layer's offset is odd.
"""
import os
import sys

os.environ["HARRIER_MINP"] = "1"        # before the model reads the geometry

import chequer7 as C
import city as T
from sam import Sam

CHUNKS = ("harness_chq5c0.asm", "harness_chq5c1.asm",   # the board's bank,
          "harness_chq5c2.asm",                         # cut by band
          "harness_chq5msk0.asm", "harness_chq5msk1.asm")


def main():
    b = Sam("harness_chq7.asm", CHUNKS, screens=(10, 12),
            chunk_defines=lambda y: {"CHQ4_RET": y["chq4_ret"]})
    s = b.syms
    b.report_memory()
    it = b.call(s["chq6_init"])
    print("  chq6_init %d T-states once, the sky into both buffers" % it)
    poses = [(x, z, t, (t // 7) % 3)
             for t, (x, z) in enumerate((x, z)
                                        for x in range(-640, 641, 20)
                                        for z in (0, 100, 900, 4321))]
    bad = 0
    times = []
    for camx, camz, t, pose in poses:
        b.poke(s["chq4_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq4_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq6_pose"], bytes([pose]))
        b.poke(s["c7_t"], bytes([t & 0xFF]))
        ts = b.call(s["chq6_frame"])
        times.append(ts)
        want = C.frame(camx, camz, t, pose)
        got = b.screen(b.shown())
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  PIXEL MISMATCH x=%d z=%d t=%d pose=%d: %d bytes, "
                      "first at %d (y=%d x=%d) got %02X want %02X"
                      % (camx, camz, t, pose, len(d), d[0], d[0] // C.STRIDE,
                         (d[0] % C.STRIDE) * 2, got[d[0]], want[d[0]]))
    n = len(poses)
    print("  %-40s %4d camera positions, %d mismatches"
          % ("Z80 against the model, pixels", n, bad))
    print("  %-40s %d of far layer, %d of near"
          % ("periods of city scrolled", n // T.STRIDE, 2 * n // T.STRIDE))
    print()
    ft = b.call(s["chq4_floor"])
    mt = b.call(s["chq4_msk8"])
    ct = b.call(s["c7_city"])
    b.call(s["chq6_frame"])             # the pose is settled in both
    b.call(s["chq6_frame"])             # buffers by the second of these
    pt = b.call(s["chq6_frame"])
    mean = sum(times) / n
    print("  chq4_floor   %7d T-states, %d scanlines of board"
          % (ft, 192 - C.TOP))
    print("  chq4_msk8    %7d T-states, the swap mask a scanline" % mt)
    print("  c7_city      %7d T-states, %d scanlines of it, two layers"
          % (ct, T.ROWS))
    print("  the pilot    %7d T-states, %d rows of it a frame"
          % (pt - ft - mt - ct, 48 + 96 - T.TOP))
    print("  chq6_frame   min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %.1f%% of a 25 Hz frame, %.1f Hz free running,"
          % ("which is", mean / 2400, 6e6 / mean))
    print("  %-40s %d Hz against the display"
          % ("", 50 // max(1, -(-int(mean) // 120000))))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
