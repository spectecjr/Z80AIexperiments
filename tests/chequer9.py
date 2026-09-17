#!/usr/bin/env python3
"""A model of chequer9: the board with a horizon that moves.

The picture is chequer8's - board, a two layer desert standing on it -
with one thing added and one taken away: the horizon is a parameter,
and the pilot is not here yet.

WHICH HORIZONS ARE ALLOWED. A band of the board is drawn whole, so the
bottom row of the screen has to be the last row of its band. 32 of the
39 rows between 40% and 60% of the screen are, which is a horizon every
scanline or two; they are numbered here as the Z80 numbers them, from
the tallest board down, because that is the order the table in
chequer9hz.z80s is in.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HARRIER_MINP"] = "1"        # chequer9's viewport: the widest
os.environ["HARRIER_HZ"] = "76"         # board it can have, which is the
os.environ["HARRIER_CAMH"] = "308"
os.environ["DESERT_ROWS"] = "24"  # a shorter band: the board can be tall      # one its bank was built for

import chequer4 as C
import desert as D
import harrier as HR

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
        if 77 <= rows <= 114:
            out.append(rows)
        rows -= n
    return out


HORIZONS = horizons()


def frame(camx, camz, hz=0):
    """hz is an index into HORIZONS: 0 is the tallest board."""
    rows = HORIZONS[hz]
    buf = C.frame(camx, camz, 191 - rows)
    top = H - rows - D.ROWS
    for r, row in enumerate(D.band(*D.offsets(camx))):
        at = (top + r) * STRIDE
        buf[at:at + STRIDE] = row
    return buf
