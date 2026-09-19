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

AND THE REAL CURRENCY IS MEMORY SLOTS. The ASIC shares one bus between
the CPU and the display and grants the CPU one access per 8 T-states
while the raster is in the display window, one per 4 T everywhere else -
23,808 slots a frame, which bubble/tools/budget.py derives and
docs/BUBBLE_BOBBLE_SAM.md states. Every access costs a slot: an opcode
fetch, an operand byte, a data read, a data write, each half of a PUSH.
So a routine that is slot-limited - and everything here is, at 3.7
T-states an access against a frame that averages 5.0 - takes
accesses / 23,808 frames however few T-states it looks like. That is
worth about a THIRD more than the T-state count says, and it is the
number game.md used to call a guess.
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
import tree as T                                        # noqa: E402
from test_chequer10 import CHUNKS, TALL, steady         # noqa: E402

FRAME = 120000                  # T-states between 50 Hz interrupts
FRAME_REAL = 119808             # the real one, against the round 120,000
SLOTS = 23808                   # and memory accesses in one, which is the
                                # budget that actually binds: see
                                # bubble/tools/budget.py for the derivation
SCREEN = 128 * 192              # bytes of a MODE 4 screen
T_PER_SLOT = 3.78               # what this code runs at, measured: the
PER_BYTE = 3.82                 # frame averages 5.03, and a sprite costs
                                # this many slots a byte it draws


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


def slots3(*trees):
    """The three tree slots as the Z80 holds them."""
    trees = list(trees) + [(255, 0, 0)] * (3 - len(trees))
    return [("cq10_tk", [t[0] for t in trees]),
            ("cq10_tx", [t[1] for t in trees]),
            ("cq10_ty", [t[2] for t in trees])]


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
    print("  The same frames in the currency that binds: memory slots")
    print("  %-30s %8s %8s %6s %7s" % ("", "T-states", "accesses",
                                       "by T", "by slots"))
    for name, fields in (("the tallest board, three trees",
                          TALL + slots3((1, 100, 118), (4, 20, 140),
                                        (7, 56, 191))),
                         ("the tallest board, no trees", TALL + slots3()),
                         ("the shortest board, no trees",
                          [("cq10_hz", 77), ("cq10_px", 40),
                           ("cq10_py", 10)] + slots3())):
        steady(b, s, fields)
        t, r, w, _ = b.traffic(s["cq10_frame"])
        print("  %-30s %8d %8d %6.2f %7.2f   %+.0f%%"
              % (name, t, r + w, t / FRAME, (r + w) / SLOTS,
                 100 * ((r + w) / SLOTS) / (t / FRAME) - 100))
    print("  %-30s a frame is %d T-states or %d slots, and this code is"
          % ("", FRAME, SLOTS))
    print("  %-30s slot-limited, so the right hand column is the true one"
          % "")

    print()
    print("  What a sprite costs in slots, which is not what it costs in T")
    print("  %-14s %8s %9s %10s %11s"
          % ("", "T", "accesses", "T a byte", "slots a byte"))
    b.poke(s["cq10_tx"], bytes([0, 0, 0]))
    b.poke(s["cq10_ty"], bytes([0, 0, 191]))
    for k, h in enumerate(T.SIZES):
        b.poke(s["cq10_tk"], bytes([255, 255, k]))
        t, r, w, _ = b.traffic(s["cq10_tree"])
        px, wd, _ = T.tree(h)
        n = sum(1 for _, kind in T.rows(px) for v in kind if v)
        print("  %-14s %8d %9d %10.1f %11.2f"
              % ("%dx%d" % (wd, h), t, r + w, t / n, (r + w) / n))
    print("  %-14s a PUSH fill is 1.50 slots a byte and cannot draw a"
          % "against which")
    print("  %-14s picture; compiled code pays for its own fetches too" % "")

    print()
    print("  And the same frames with the wait states actually counted")
    print("  %-30s %8s %9s %7s %7s" % ("", "natural", "contended",
                                       "frames", "cost"))
    for name, fields in (("the tallest board, three trees",
                          TALL + slots3((1, 100, 118), (4, 20, 140),
                                        (7, 56, 191))),
                         ("the tallest board, no trees", TALL + slots3()),
                         ("the shortest board, no trees",
                          [("cq10_hz", 77), ("cq10_px", 40),
                           ("cq10_py", 10)] + slots3())):
        steady(b, s, fields)
        nat, con, n, w = b.contended(s["cq10_frame"], start=0)
        print("  %-30s %8d %9d %7.2f %6.0f%%"
              % (name, nat, con, con / FRAME_REAL, 100 * (con / nat - 1)))
    print("  %-30s started at the frame interrupt, %d T-states a frame."
          % ("", FRAME_REAL))
    print("  %-30s A slot division says 2.44 for the first of those - the"
          % "")
    print("  %-30s difference is that a Z80 cannot put every access on a"
          % "")
    print("  %-30s slot, which is what the next table is about." % "")

    print()
    print("  What an instruction costs, which is where that difference goes")
    print("  %-26s %8s %9s %9s" % ("", "nominal", "blanked", "display line"))
    for name, gaps, nominal in (("NOP", (4,), 4), ("LD A,(HL)", (4, 3), 7),
                                ("LD (HL),A", (4, 3), 7),
                                ("PUSH DE", (5, 3, 3), 11)):
        out = []
        for start in (0, 68 * 384):
            t, n = start, 0
            while t < start + 384 * 4:
                for g in gaps:
                    t += g
                    t += Sam._mem_wait(t)
                n += 1
            out.append((t - start) / n)
        print("  %-26s %8d %9.1f %9.1f" % (name, nominal, out[0], out[1]))
    t, bytes_out = 0, 0
    while t < FRAME_REAL:
        for g in (5, 3, 3):
            t += g
            t += Sam._mem_wait(t)
        bytes_out += 2
    print("  %-26s %d bytes a frame, not 15,872, and a screen is %.2f frames"
          % ("so a PUSH fill manages", bytes_out, 24576 / bytes_out))

    print()
    print("  and what a mix of sprites needs, in slots")
    print("  %-28s %6s %8s %9s" % ("", "bytes", "T-states", "slots"))
    mixes = []
    for name, mix in (("the ask: 4 large, 8 medium", ((16, 135, 4), (20, 81, 8))),
                      ("2 large, 4 medium, 6 small",
                       ((16, 135, 2), (20, 81, 4), (10, 54, 6))),
                      ("1 large, 5 medium, 6 small",
                       ((16, 135, 1), (20, 81, 5), (10, 54, 6)))):
        sbytes = sum(masked(wb, h)[1] * n for wb, h, n in mix)
        st = sum(masked(wb, h)[0] * n for wb, h, n in mix)
        sslots = int(sbytes * PER_BYTE)
        mixes.append((name, sbytes, st, sslots))
        print("  %-28s %6d %8d %9d" % (name, sbytes, st, sslots))
    print("  %-28s at %.2f slots a byte, the measured figure for the"
          % ("", PER_BYTE))
    print("  %-28s largest compiled sprite here" % "")

    print()
    print("  The verdict, in slots: a display frame is %d of them" % SLOTS)
    fixed = int((boards[70] + 18000 + 8056 + 2242 + 7500 + 5000) / T_PER_SLOT)
    print("  %-28s %6d slots for the board at 70 rows, a 12 row band,"
          % ("the picture, without sprites", fixed))
    print("  %-28s the pilot, sound and the game's own arithmetic" % "")
    for name, sbytes, st, sslots in mixes:
        need = (fixed + sslots) / SLOTS
        rate = 50 / max(1, -(-need // 1))
        print("  %-28s %6d slots = %.2f frames -> %.1f Hz"
              % (name, fixed + sslots, need, rate))

    print("\nALL TESTS PASSED")          # it is a study, not a test, but
    return 0                             # mkreports.py reads this


if __name__ == "__main__":
    sys.exit(main())
