#!/usr/bin/env python3
"""Verify and time chequer9 - the board with a horizon that moves.

    pip install z80
    python3 tests/test_chequer9.py

The horizon runs from row 172 to row 95 - the board taking 10% of the
screen to 50% of it - and every one of the 65 positions in between is
drawn and compared whole, at a different camera each. One run bank
serves all of them, because a square's width depends on the row's
distance from the horizon and not on the row.

The sweep also walks the horizon up and down rather than jumping about,
because a board that shrinks leaves rows behind it that nothing else
paints, and putting those back is per buffer.
"""
import os
import sys

os.environ["HARRIER_MINP"] = "1"        # chequer9's viewport
os.environ["DESERT_PAL"] = "board4"     # and the desert drawn in them
os.environ["CHQ_SWAP"] = "0xBB"         # a board in four colours
os.environ["JET_PAL"] = "board4"
os.environ["JET_W"] = "24"              # chequer9's pilot, 24x48
os.environ["JET_H"] = "48"
os.environ["HARRIER_SKY"] = "15"        # a flat sky and a flat board:
os.environ["DESERT_SKY"] = "15"         # nothing here grades a palette
os.environ["HARRIER_HZ"] = "95"
os.environ["HARRIER_CAMH"] = "308"
os.environ["DESERT_ROWS"] = "20"  # a shorter band: the board can be tall

import chequer9 as C
import desert as T
import jetpack as J
from sam import Sam

CHUNKS = ("harness_chq9c0.asm", "harness_chq9c1.asm",   # the board's bank,
          "harness_chq9c2.asm",                         # widest bands first
          "harness_chq9msk0.asm", "harness_chq9msk1.asm",   # the swap masks
          "harness_chq9c3.asm", "harness_chq9c4.asm",   # and the rest of it
          "harness_desert9_0.asm", "harness_desert9_1.asm",
          "harness_jetmove.asm")                        # and the pilot


def corner(i, hz):
    """Where the pilot is, and which pose, for frame i of the sweep.

    He goes round the four corners of the screen while the horizon
    walks, which is what the demo does - the difference being that here
    he takes big steps, so that the sky he leaves behind is a fresh
    piece of the screen every frame rather than a sliver.
    """
    px = (i * 13) % (128 - J.W // 2)
    py = (i * 7) % (192 - J.H)
    return px, py, i % 3


def main():
    b = Sam("harness_chq9.asm", CHUNKS, screens=(10, 12),
            chunk_defines=lambda y: {"CHQ4_RET": y["chq4_ret"],
                                     "CHQ4_SCR": y["CHQ4_SCREEN"],
                                     "C9_RET": y["c9_ret"],
                                     "CQ9_R": y["cq9_ret"]})
    s = b.syms
    b.report_memory()
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
        px, py, pose = corner(i, hz)
        b.poke(s["chq4_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq4_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["cq9_hz"], bytes([hz]))
        b.poke(s["cq9_px"], bytes([px]))
        b.poke(s["cq9_py"], bytes([py]))
        b.poke(s["cq9_pose"], bytes([pose]))
        times.append(b.call(s["cq9_frame"]))
        got = b.screen(b.shown())
        want = bytes(C.frame(camx, camz, hz, px, py, pose))
        if got != want:
            bad += 1
            if bad <= 3:
                d = [k for k in range(len(want)) if got[k] != want[k]]
                print("  PIXEL MISMATCH hz=%d (%d rows) x=%d px=%d py=%d: "
                      "%d bytes, first at %d (y=%d x=%d) got %02X want %02X"
                      % (hz, C.HORIZONS[hz], camx, px, py, len(d), d[0],
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

    print()                             # and what a real SAM would be
    for hz, name in ((0, "tallest"), (n - 1, "shortest")):   # charged
        for _ in range(2):              # contention on: a copy of the
            b.poke(s["cq9_hz"], bytes([hz]))    # resident block sits behind
            b.poke(s["cq9_px"], bytes([56]))    # each buffer, so both want
            b.poke(s["cq9_py"], bytes([0 if hz else 144]))   # feeding
            b.call(s["cq9_frame"])
        t, r, w, scr = b.traffic(s["cq9_frame"])
        print("  memory traffic, %-9s board %7d cycles, one every %.2f"
              " T-states" % (name, r + w, t / (r + w)))
        print("  %-40s %d of them bytes onto the screen" % ("", scr))
    print("  %-40s 3.67 T-states a cycle" % "a PUSH fill, for scale, is")

    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
