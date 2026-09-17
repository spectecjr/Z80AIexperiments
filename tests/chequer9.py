#!/usr/bin/env python3
"""A model of chequer9: the board with a horizon that moves.

The picture is chequer8's - board, a two layer desert standing on it -
with one thing added and one taken away: the horizon is a parameter,
and the pilot is not here yet.

WHICH HORIZONS ARE ALLOWED. A band of the board is drawn whole, so the
bottom row of the screen has to be the last row of its band. 65 of the
78 rows between 10% of the screen and 50% of it are - near the horizon
a band is a scanline or two, so nearly every row is allowed, and it is
the wide bands at the bottom of the screen that rule out runs of them.
They are numbered here as the Z80 numbers them, from the tallest board
down, because that is the order the table in chequer9hz.z80s is in.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HARRIER_MINP"] = "1"        # chequer9's viewport: the widest
os.environ["HARRIER_HZ"] = "95"         # board it can have, which is the
os.environ["HARRIER_CAMH"] = "308"      # one its bank was built for
os.environ["DESERT_ROWS"] = "20"        # and a shorter band than
                                        # chequer8's, so that the tallest
                                        # board still fits the frame
ROWS0, ROWS1 = 19, 96                   # the range of boards a horizon
                                        # may give: 10% of the screen to
                                        # 50% of it

import chequer4 as C
import desert as D
import harrier as HR
import jetpack as J

W, H, STRIDE = C.W, C.H, C.STRIDE


def horizons():
    """How many scanlines of board each allowed horizon gives, tallest
    first - which is the Z80's index into chq4_hztab."""
    out, rows, run, last = [], H - 1 - HR.HZ, 0, None
    widths = [HR.PTAB[y] for y in range(H - 1, HR.HZ, -1)]   # bottom up
    bands = []
    for p in widths:
        if p == last:
            run += 1
        else:
            if last is not None:
                bands.append(run)
            run, last = 1, p
    bands.append(run)
    for n in bands:
        if ROWS0 <= rows <= ROWS1:
            out.append(rows)
        rows -= n
    return out


HORIZONS = horizons()


def frame(camx, camz, hz=0, px=56, py=48, pose=1):
    """hz is an index into HORIZONS: 0 is the tallest board.

    px is the pilot's left hand byte and py his top row - he moves in
    whole bytes sideways, which is two pixels, and in whole scanlines.
    """
    rows = HORIZONS[hz]
    buf = C.frame(camx, camz, 191 - rows)
    top = H - rows - D.ROWS
    for r, row in enumerate(D.band(*D.offsets(camx))):
        at = (top + r) * STRIDE
        buf[at:at + STRIDE] = row
    for y, (by, kind) in enumerate(J.rows(J.lean(J.pilot(), pose - 1))):
        base = (py + y) * STRIDE + px
        for i, b in enumerate(by):
            if kind[i] == 1:
                buf[base + i] = b
            elif kind[i] == 2:                  # the pilot's left pixel
                buf[base + i] = b | (buf[base + i] & 0x0F)
            elif kind[i] == 3:                  # and its right one
                buf[base + i] = b | (buf[base + i] & 0xF0)
    return buf
