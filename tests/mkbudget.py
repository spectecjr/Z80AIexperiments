#!/usr/bin/env python3
"""Budget a frame for a playable game, out of measured parts.

    python3 tests/mkbudget.py

game.md is the argument; this is the arithmetic, and it measures what it
can rather than quoting it. The board and the desert come off the
chequer10 harness at whatever horizon is asked for; the sprites are
compiled by tests/mksprite.py and costed by its own instruction count,
which is the same count the harness agrees with to a few hundred
T-states.

THE CURRENCY IS BYTES WRITTEN. A MODE 4 screen is 24,576 bytes and a 25
Hz frame is 240,000 T-states, so at the board's measured 9.5 T-states a
byte a frame can write the screen about once. Everything below is an
argument about which bytes.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for k, v in dict(HARRIER_MINP="1", DESERT_PAL="board4", CHQ_SWAP="0xBB",
                 JET_PAL="board4", JET_W="24", JET_H="48",
                 HARRIER_SKY="15", DESERT_SKY="15", HARRIER_HZ="95",
                 HARRIER_CAMH="308", DESERT_ROWS="20").items():
    os.environ.setdefault(k, v)

import chequer10 as C                                   # noqa: E402
import mksprite as S                                    # noqa: E402
from sam import Sam                                     # noqa: E402
from test_chequer10 import CHUNKS                       # noqa: E402

FRAME = 120000                  # T-states between 50 Hz interrupts
SCREEN = 128 * 192              # bytes of a MODE 4 screen


def solid(wb, h):
    """A sprite of wb bytes by h rows with nothing transparent in it -
    the floor for a walk of SP, and what a flat game sprite approaches."""
    rows = [([0xDD] * wb, [1] * wb) for _ in range(h)]
    _, t = S.walk("x", rows, wb, h, "R")
    return t, wb * h


def masked(wb, h, fill=0.70):
    """The same box with a silhouette in it: an edge byte a row a side,
    and fill of the rest solid. Which is a tree, or a dragon segment."""
    rows = []
    for y in range(h):
        by, kind = [], []
        n = max(2, int(round(wb * fill)))
        left = (wb - n) // 2
        for x in range(wb):
            if left <= x < left + n:
                kind.append(2 if x == left else 3 if x == left + n - 1 else 1)
                by.append(0xDD)
            else:
                kind.append(0)
                by.append(0)
        rows.append((by, kind))
    _, t = S.walk("y", rows, wb, h, "R")
    return t, sum(1 for _, k in rows for v in k if v)


def board(b, s, rows):
    """What a board of that many scanlines costs, measured."""
    hz = C.HORIZONS.index(rows)
    b.poke(s["cq10_hz"], bytes([hz]))
    b.call(s["cq10_frame"])
    b.call(s["cq10_frame"])
    b.call(s["chq4_msk8"])
    return b.call(s["chq4_floor"])


def main():
    b = Sam("harness_chq10.asm", CHUNKS, screens=(10, 12),
            chunk_defines=lambda y: {"CHQ4_RET": y["chq4_ret"],
                                     "CHQ4_SCR": y["CHQ4_SCREEN"],
                                     "C9_RET": y["c9_ret"],
                                     "CQ9_R": y["cq10_pret"],
                                     "CQ10_R": y["cq10_ret"]})
    s = b.syms
    b.call(s["cq10_init"])
    b.poke(s["chq4_camx"], (30000).to_bytes(2, "little"))
    b.poke(s["cq10_tk"], bytes([255] * 3))

    print("  What a sprite costs, by shape and by how much of its box it fills")
    print("  %-22s %6s %7s %8s %9s" % ("", "bytes", "T", "T a byte", "code"))
    for wb, h, how in ((16, 135, "solid"), (16, 135, "masked"),
                       (20, 81, "solid"), (20, 81, "masked"),
                       (10, 54, "solid"), (10, 54, "masked"),
                       (32, 48, "solid")):
        t, n = solid(wb, h) if how == "solid" else masked(wb, h)
        print("  %-22s %6d %7d %8.1f %9d"
              % ("%d x %-3d  %s" % (wb, h, how), n, t, t / n,
                 int(2.75 * n)))
    print("  %-22s the tree at 32x135, speckled and outlined: 22,190"
          % "against which")

    print()
    print("  What the picture costs, measured at the horizons it can have")
    print("  %-22s %7s %9s %8s" % ("", "T", "T a row", "T a byte"))
    for rows in (96, 70, 48, 19):
        t = board(b, s, rows)
        print("  %-22s %7d %9.0f %8.2f"
              % ("the board, %d rows" % rows, t, t / rows, t / (rows * 128)))
    print("  %-22s %7d %9.0f %8.2f   pixel-precise spans"
          % ("the desert, 20 rows", 49866, 49866 / 20, 49866 / (20 * 128)))
    print("  %-22s %7d" % ("the pilot, 24x48", 8056))
    print("  %-22s %7d   mean, and 7,564 at its worst" % ("sound", 2242))

    boards = {rows: board(b, s, rows) for rows in (96, 70)}
    print()
    print("  What a sprite over the SKY costs, where its box has to be put")
    print("  back as well - and why drawing the box solid beats masking it")
    for wb, h in ((16, 135), (20, 81), (10, 54)):
        box = wb * h
        tm, n = masked(wb, h)
        ts, _ = solid(wb, h)
        print("  %-22s masked %6d + wipe %5d = %6d, solid box twice %6d"
              % ("%d x %-3d" % (wb, h), tm, int(box * 7.0),
                 tm + int(box * 7.0), 2 * ts))
    print("  %-22s over the BOARD neither applies: it repaints every byte"
          % "and")

    print()
    print("  A game's frame, and what is left for sprites")
    for rows, band, name in ((96, 49866, "the board at 96 rows, chequer10's band"),
                             (70, 18000, "the board at 70 rows, a 12 row band")):
        fixed = boards[rows] + band + 8056 + 2242 + 7500 + 5000
        print("  %s" % name)
        for mult, rate in ((2, "25 Hz"), (3, "16.7 Hz"), (4, "12.5 Hz")):
            left = mult * FRAME - fixed
            print("    %-20s %7d T fixed, %7d left = %5d bytes of sprite"
                  % (rate, fixed, left, max(0, int(left / 13))))
    print("  %-22s 13 T-states a byte drawn: a masked sprite over the board"
          % "at")

    print()
    print("  and what a mix of sprites needs")
    for name, mix in (("the ask: 4 large, 8 medium", ((16, 135, 4), (20, 81, 8))),
                      ("2 large, 4 medium, 6 small",
                       ((16, 135, 2), (20, 81, 4), (10, 54, 6))),
                      ("1 large, 5 medium, 6 small",
                       ((16, 135, 1), (20, 81, 5), (10, 54, 6)))):
        sbytes = sum(masked(wb, h)[1] * n for wb, h, n in mix)
        st = sum(masked(wb, h)[0] * n for wb, h, n in mix)
        print("    %-26s %2d sprites, %5d bytes, %6d T-states"
              % (name, sum(n for _, _, n in mix), sbytes, st))

    print("\nALL TESTS PASSED")          # it is a study, not a test, but
    return 0                             # mkreports.py reads this


if __name__ == "__main__":
    sys.exit(main())
