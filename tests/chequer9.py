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
os.environ["JET_W"] = "24"              # a smaller pilot: 24x48 where
os.environ["JET_H"] = "48"              # chequer6 to 8 have him 32x96
os.environ["HARRIER_SKY"] = "15"        # a flat sky, in an index of its
os.environ["DESERT_SKY"] = "15"         # own: no palette changes by
                                        # scanline anywhere in this demo,
                                        # because a SAM services those
                                        # with a line interrupt a row
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
    """How many scanlines of board each horizon gives, tallest first -
    which is the Z80's index into chq4_hztab.

    Every row in the range is a horizon now. A shallow board is the deep
    one with scanlines left out rather than a rescaled copy of it, so
    each horizon carries a band list of its own and nothing has to fall
    on a band boundary.
    """
    return list(range(ROWS1, ROWS0 - 1, -1))


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
