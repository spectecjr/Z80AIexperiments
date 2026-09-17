#!/usr/bin/env python3
"""Verify and time chequer8 - everything on the screen, every frame.

    pip install z80
    python3 tests/test_chequer8.py

The picture is chequer7's and the model is chequer7's. What is checked
here is that the compiled pilot in his own page puts down exactly the
bytes the stream player did, over a board and a city that are redrawn
under him every frame - so the sweep drives poses and city offsets
together, and every frame is compared whole.
"""
import os
import sys

os.environ["HARRIER_MINP"] = "1"        # before the model reads the geometry
os.environ["HARRIER_HZ"] = "114"        # chequer8's viewport is its own
os.environ["HARRIER_CAMH"] = "308"

import chequer8 as C
import desert as T
from sam import Sam

CHUNKS = ("harness_chq8c0.asm", "harness_chq8c1.asm",   # the board's bank,
          "harness_chq8c2.asm",                         # cut by band
          "harness_chq8msk0.asm", "harness_chq8msk1.asm",
          "harness_jetrun.asm",                         # the pilot, and
          "harness_desert0.asm", "harness_desert1.asm",  # and the rear
          "harness_desert2.asm")                         # layer's rows


def main():
    b = Sam("harness_chq8.asm", CHUNKS, screens=(10, 12),
            chunk_defines=lambda y: {"CHQ4_RET": y["chq4_ret"],
                                     "CHQ4_SCR": y["CHQ4_SCREEN"],
                                     "C9_RET": y["c9_ret"]})
    s = b.syms
    for name, equ in (("harness_jetrun.asm", "JET8_BANK"),
                      ("harness_desert0.asm", "C9_BANK0")):
        page = b.pages[CHUNKS.index(name)]
        print("  %-22s page %2d, and %s says %2d"
              % (name, page, equ, s[equ] & 31))
        assert page == s[equ] & 31, "the map and the constant disagree"
    it = b.call(s["c8_init"])
    print("  c8_init   %d T-states once, the sky into both buffers" % it)
    poses = [(x, z, t, (t // 7) % 3)
             for t, (x, z) in enumerate((x, z)
                                        for x in range(-640, 641, 20)
                                        for z in (0, 100, 900, 4321))]
    bad, times = 0, []
    for camx, camz, t, pose in poses:
        b.poke(s["chq4_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq4_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["c8_pose"], bytes([pose]))
        b.poke(s["c9_far"], bytes([(t // T.REAR_EVERY) & 0xFF]))
        b.poke(s["c9_near"], bytes([t & 0xFF]))
        times.append(b.call(s["c8_frame"]))
        got = b.screen(b.shown())
        if got != bytes(C.frame(camx, camz, t, pose)):
            bad += 1
            want = bytes(C.frame(camx, camz, t, pose))
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  PIXEL MISMATCH x=%d z=%d t=%d pose=%d: %d bytes, "
                      "first at %d (y=%d x=%d) got %02X want %02X"
                      % (camx, camz, t, pose, len(d), d[0], d[0] // C.STRIDE,
                         (d[0] % C.STRIDE) * 2, got[d[0]], want[d[0]]))
    n = len(poses)
    print("  %-40s %4d camera positions, %d mismatches"
          % ("Z80 against the model, pixels", n, bad))
    print()
    ft = b.call(s["chq4_floor"])
    mt = b.call(s["chq4_msk8"])
    ct = b.call(s["c9_band"])
    pt = b.call(s["c8_frame"])
    mean = sum(times) / n
    print("  chq4_floor   %7d T-states, %d scanlines of board"
          % (ft, 192 - C.TOP))
    print("  chq4_msk8    %7d T-states, the swap mask a scanline" % mt)
    print("  c9_band      %7d T-states, %d scanlines of desert, two layers"
          % (ct, T.ROWS))
    print("  the pilot    %7d T-states, all 96 rows of him, compiled"
          % (pt - ft - mt - ct))
    print("  c8_frame     min %7d  mean %7.0f  max %7d"
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
