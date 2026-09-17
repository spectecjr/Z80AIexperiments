#!/usr/bin/env python3
"""Verify and time chequer9 - the board with a horizon that moves.

    pip install z80
    python3 tests/test_chequer9.py

The horizon runs from row 114 to row 77 - 40% of the screen to 59% -
and every one of the 32 positions in between is drawn and compared
whole, at several cameras each. One run bank serves all of them,
because a square's width depends on the row's distance from the
horizon and not on the row.

The sweep also walks the horizon up and down rather than jumping about,
because a board that shrinks leaves rows behind it that nothing else
paints, and putting those back is per buffer.
"""
import os
import sys

os.environ["HARRIER_MINP"] = "1"        # chequer9's viewport
os.environ["HARRIER_HZ"] = "76"
os.environ["HARRIER_CAMH"] = "308"
os.environ["DESERT_ROWS"] = "24"  # a shorter band: the board can be tall

import chequer9 as C
import desert as T
from sam import Sam

CHUNKS = ("harness_chq9c0.asm", "harness_chq9c1.asm",   # the board's bank,
          "harness_chq9c2.asm",                         # widest bands first
          "harness_chq9msk0.asm", "harness_chq9msk1.asm",   # the swap masks
          "harness_chq9c3.asm", "harness_chq9c4.asm",   # and the rest of
          "harness_chq9c5.asm",                         # the bank
          "harness_desert9_0.asm", "harness_desert9_1.asm")


def main():
    b = Sam("harness_chq9.asm", CHUNKS, screens=(10, 12),
            chunk_defines=lambda y: {"CHQ4_RET": y["chq4_ret"],
                                     "CHQ4_SCR": y["CHQ4_SCREEN"],
                                     "C9_RET": y["c9_ret"]})
    s = b.syms
    print("  %-40s %d, pages %s"
          % ("chunks", len(CHUNKS), ", ".join(str(p) for p in b.pages)))
    it = b.call(s["cq9_init"])
    print("  cq9_init  %d T-states once, the sky into both buffers" % it)

    n = len(C.HORIZONS)
    walk = list(range(n)) + list(range(n - 1, -1, -1))   # up and back down
    bad, times = 0, []
    for i, hz in enumerate(walk):
        camx = -3000 + 211 * i
        camz = 900 * (i % 5)
        b.poke(s["chq4_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq4_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["cq9_hz"], bytes([hz]))
        times.append(b.call(s["cq9_frame"]))
        got = b.screen(b.shown())
        want = bytes(C.frame(camx, camz, hz))
        if got != want:
            bad += 1
            if bad <= 3:
                d = [k for k in range(len(want)) if got[k] != want[k]]
                print("  PIXEL MISMATCH hz=%d (%d rows) x=%d z=%d: %d bytes, "
                      "first at %d (y=%d x=%d) got %02X want %02X"
                      % (hz, C.HORIZONS[hz], camx, camz, len(d), d[0],
                         d[0] // C.STRIDE, (d[0] % C.STRIDE) * 2,
                         got[d[0]], want[d[0]]))
    print("  %-40s %d frames, %d horizons, %d mismatches"
          % ("Z80 against the model, pixels", len(walk), n, bad))
    print("  %-40s %d rows (%.0f%%) to %d rows (%.0f%%)"
          % ("the board runs", C.HORIZONS[-1], 100 * C.HORIZONS[-1] / 192,
             C.HORIZONS[0], 100 * C.HORIZONS[0] / 192))
    print()
    lo = times[:n]
    print("  cq9_frame at the shortest board  %7d T-states" % min(lo))
    print("  cq9_frame at the tallest board   %7d T-states" % max(lo))
    print("  %-40s %.1f%% of a 25 Hz frame at its worst"
          % ("which is", max(times) / 2400))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
