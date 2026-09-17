#!/usr/bin/env python3
"""Verify and time chequer10 - three trees standing on the moving board.

    pip install z80
    python3 tests/test_chequer10.py

chequer9's sweep with scenery in it: every horizon from 10% of the
screen to 50% of it, the pilot going round the screen, and three trees
coming in from the distance through all eight of their sizes. Every
sprite leaves a box of sky behind it when it moves, and putting that
back is per buffer - so the sweep walks the horizon up and down and
moves all four of them every frame rather than jumping about.
"""
import os
import sys

os.environ["HARRIER_MINP"] = "1"        # chequer9's viewport, whole
os.environ["DESERT_PAL"] = "board4"
os.environ["CHQ_SWAP"] = "0xBB"
os.environ["JET_PAL"] = "board4"
os.environ["JET_W"] = "24"
os.environ["JET_H"] = "48"
os.environ["HARRIER_SKY"] = "15"
os.environ["DESERT_SKY"] = "15"
os.environ["HARRIER_HZ"] = "95"
os.environ["HARRIER_CAMH"] = "308"
os.environ["DESERT_ROWS"] = "20"

import chequer10 as C
import harrier as HR
import jetpack as J
import tree as T
from sam import Sam

CHUNKS = ("harness_chq9c0.asm", "harness_chq9c1.asm",   # the board's bank,
          "harness_chq9c2.asm",                         # widest bands first
          "harness_chq9msk0.asm", "harness_chq9msk1.asm",   # the swap masks
          "harness_chq9c3.asm", "harness_chq9c4.asm",   # and the rest of it
          "harness_desert9_0.asm", "harness_desert9_1.asm",
          "harness_jetmove.asm",                        # the pilot,
          "harness_tree.asm")                           # and the scenery


def corner(i):
    """Where the pilot is, and which pose, for frame i of the sweep."""
    px = (i * 13) % (128 - J.W // 2)
    py = (i * 7) % (192 - J.H)
    return px, py, i % 3


def standing(i, hz, camx, camz):
    """Three trees, furthest first: one at the depth that asks for size
    i % 8 and two further out, spread across the board - so every size
    is drawn at every part of the sweep, and the slots are always in
    the order the Z80 draws them in."""
    out = []
    for j in range(C.SLOTS):
        k = (i + 2 * j) % len(T.SIZES)
        d = TREEH * HR.FOCAL / T.SIZES[k]
        x = camx + (((i * 37 + 83 * j) % 9) - 4) * 256
        out.append((d, C.place(hz, camx, camz, x, camz + d)))
    out.sort(key=lambda p: -p[0])       # furthest first
    return [at if at else (255, 0, 0) for _, at in out]


TREEH = C.TREEH


CAM = (30000, 0)                        # a camera to hold still while
                                        # the scenery is timed
TALL = [("cq10_hz", 0),                 # the tallest board, which is
        ("cq10_px", 40), ("cq10_py", 10)]       # the dearest one to
                                        # draw, and the pilot pinned: a
                                        # sprite that moves is a box of
                                        # sky to put back as well


def steady(b, s, fields):
    """One frame's cost with the state settled in both buffers.

    Everything the caller pokes lands in the copy of the resident block
    behind the buffer about to be drawn, and there is one behind each -
    the camera included, which is what makes a board cost what it does.
    So a setting has to be poked for both buffers before what it costs
    is what it would cost in a demo. Values are bytes, so that a whole
    row of tree slots can be poked at once.
    """
    for _ in range(3):
        b.poke(s["chq4_camx"], CAM[0].to_bytes(2, "little"))
        b.poke(s["chq4_camz"], CAM[1].to_bytes(2, "little"))
        for a, v in fields:
            b.poke(s[a], bytes(v) if isinstance(v, (list, tuple)) else
                   bytes([v]))
        t = b.call(s["cq10_frame"])
    return t


def slots(*trees):
    """The three slots as the Z80 holds them: sizes, lefts, rows."""
    trees = list(trees) + [(255, 0, 0)] * (C.SLOTS - len(trees))
    return [("cq10_tk", [t[0] for t in trees]),
            ("cq10_tx", [t[1] for t in trees]),
            ("cq10_ty", [t[2] for t in trees])]


def main():
    b = Sam("harness_chq10.asm", CHUNKS, screens=(10, 12),
            chunk_defines=lambda y: {"CHQ4_RET": y["chq4_ret"],
                                     "CHQ4_SCR": y["CHQ4_SCREEN"],
                                     "C9_RET": y["c9_ret"],
                                     "CQ9_R": y["cq10_pret"],
                                     "CQ10_R": y["cq10_ret"]})
    s = b.syms
    print("  %-40s %d, pages %s"
          % ("chunks", len(CHUNKS), ", ".join(str(p) for p in b.pages)))
    it = b.call(s["cq10_init"])
    print("  cq10_init %d T-states once, the sky into both buffers" % it)

    n = len(C.HORIZONS)
    walk = list(range(n)) + list(range(n - 1, -1, -1))   # up and back down
    bad, times, seen = 0, [], set()
    for i, hz in enumerate(walk):
        camx = -3000 + 211 * i
        camz = 900 * (i % 5)
        px, py, pose = corner(i)
        trees = standing(i, hz, camx, camz)
        seen |= {tk for tk, _, _ in trees}
        b.poke(s["chq4_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq4_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["cq10_hz"], bytes([hz]))
        b.poke(s["cq10_px"], bytes([px]))
        b.poke(s["cq10_py"], bytes([py]))
        b.poke(s["cq10_pose"], bytes([pose]))
        b.poke(s["cq10_tk"], bytes(t[0] for t in trees))
        b.poke(s["cq10_tx"], bytes(t[1] for t in trees))
        b.poke(s["cq10_ty"], bytes(t[2] for t in trees))
        times.append(b.call(s["cq10_frame"]))
        got = b.screen(b.shown())
        want = bytes(C.frame(camx, camz, hz, px, py, pose, trees))
        if got != want:
            bad += 1
            if bad <= 3:
                d = [k for k in range(len(want)) if got[k] != want[k]]
                print("  PIXEL MISMATCH hz=%d (%d rows) x=%d px=%d py=%d "
                      "trees=%s: %d bytes, first at %d (y=%d x=%d) "
                      "got %02X want %02X"
                      % (hz, C.HORIZONS[hz], camx, px, py, trees,
                         len(d), d[0], d[0] // C.STRIDE,
                         (d[0] % C.STRIDE) * 2, got[d[0]], want[d[0]]))
    print("  %-40s %d frames, %d horizons, %d mismatches"
          % ("Z80 against the model, pixels", len(walk), n, bad))
    print("  %-40s %s" % ("the tree drawn at sizes",
                          ", ".join(str(T.SIZES[k]) for k in sorted(seen)
                                    if k < len(T.SIZES))))
    print()
    lo = times[:n]
    print("  cq10_frame at the shortest board %7d T-states" % min(lo))
    print("  cq10_frame at the tallest board  %7d T-states" % max(lo))
    print("  %-40s %.1f%% of a 25 Hz frame at its worst"
          % ("which is", max(times) / 2400))

    print()                             # what the scenery costs, at the
    drawn = []                          # board that leaves it the least
    for k in range(len(T.SIZES)):       # room
        b.poke(s["cq10_tk"], bytes([255, 255, k]))
        b.poke(s["cq10_tx"], bytes([0, 0, 0]))
        b.poke(s["cq10_ty"], bytes([0, 0, 191]))
        drawn.append(b.call(s["cq10_tree"]))
    base = steady(b, s, TALL + slots())
    for k, h in enumerate(T.SIZES):
        t = steady(b, s, TALL + slots((k, 0, 191)))
        print("  the tree at %3d scanlines        %6d T-states drawn, %6d"
              " in the frame" % (h, drawn[k], t - base))
    three = steady(b, s, TALL + slots((1, 100, 118), (4, 20, 140),
                                      (7, 56, 191)))
    print("  %-40s %6d T-states, %d in the frame"
          % ("three of them, 19 + 54 + 135 rows",
             drawn[1] + drawn[4] + drawn[7], three - base))
    worst = steady(b, s, [("cq10_hz", 0), ("cq10_px", 0), ("cq10_py", 0)]
                   + slots((1, 100, 118), (4, 20, 140), (7, 56, 191)))
    print("  %-40s %7d T-states" % ("the worst frame there is", worst))
    print("  %-40s %.1f%% of a 25 Hz frame" % ("which is", worst / 2400))

    print()                             # and what a real SAM would be
    for trees, name in ((((1, 100, 118), (4, 20, 140), (7, 56, 191)),
                         "with three trees"), ((), "with none")):
        steady(b, s, TALL + slots(*trees))
        t, r, w, scr = b.traffic(s["cq10_frame"])
        print("  memory traffic, %-16s %7d cycles, one every %.2f T-states"
              % (name, r + w, t / (r + w)))
        print("  %-40s %d of them bytes onto the screen" % ("", scr))
    print("  %-40s 3.67 T-states a cycle" % "a PUSH fill, for scale, is")

    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
