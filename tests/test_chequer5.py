#!/usr/bin/env python3
"""Verify and time chequer5 - chequer4's routine, board to the horizon.

    pip install z80
    python3 tests/test_chequer5.py

Same code as chequer4.z80s, byte for byte: only the viewport changes.
Where chequer4 stops at eight-pixel squares and lets a haze meet the sky,
this draws every row down to squares one pixel wide, which is eleven more
scanlines and seven more widths.

The bank is paged, so this runs on tests/sam.py's emulation of LMPR,
HMPR and VMPR rather than on a flat 64K, and reads a buffer back out of
physical RAM - after the flip the buffer just drawn is the one the video
hardware is displaying, and it is not mapped at all.
"""
import os
import sys

os.environ["HARRIER_MINP"] = "1"        # before the model reads the geometry

import chequer4 as C
from sam import Sam

CHUNKS = ("harness_chq5bank.asm", "harness_chq5msk0.asm",
          "harness_chq5msk1.asm")


def main():
    b = Sam("harness_chq5.asm", CHUNKS, screens=(6, 8),
            chunk_defines=lambda y: {"CHQ4_RET": y["chq4_ret"]})
    s = b.syms
    it = b.call(s["chq4_init"])
    print("  chq4_init %d T-states once, the sky into both buffers" % it)
    # camx runs past one square and goes negative, because the square
    # the camera is standing in is a parity of its own
    poses = [(x, z) for x in range(-640, 641, 47) for z in (0, 100, 900, 4321)]
    bad = 0
    times = []
    for camx, camz in poses:
        b.poke(s["chq4_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq4_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        t = b.call(s["chq4_frame"])
        times.append(t)
        want = C.frame(camx, camz)
        got = b.screen(b.shown())       # the flip shows what was drawn
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  PIXEL MISMATCH x=%d z=%d: %d bytes, first at %d "
                      "(y=%d x=%d p=%d) got %02X want %02X"
                      % (camx, camz, len(d), d[0], d[0] // C.STRIDE,
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
    mean = sum(times) / n
    print("  chq4_floor   %7d T-states, %d scanlines of board"
          % (ft, 192 - C.TOP))
    print("  chq4_msk8    %7d T-states, the swap mask a scanline" % mt)
    print("  chq4_frame   min %7d  mean %7.0f  max %7d"
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
