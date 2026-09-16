#!/usr/bin/env python3
"""A model of chequer7: chequer6, with a city between board and sky.

The order is the order the Z80 draws in and it matters, because the
three things overlap: the board from row 97 down, the city over the
sixteen rows above it, and the pilot over the top of both.

WHERE THE PILOT DIVIDES MOVES. chequer6 draws the pilot's rows above
the board once per buffer, because nothing paints over them; here the
city does, so the division goes up to the city's top row and sixteen
more rows of pilot are redrawn every frame.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HARRIER_MINP"] = "1"

import chequer4 as C
import city as T
import jetpack as J
from mkjetdata import X, Y

W, H, STRIDE, TOP, PTAB = C.W, C.H, C.STRIDE, C.TOP, C.PTAB


def frame(camx, camz, t, pose=1):
    """pose 0 banks left, 1 is level, 2 banks right; t is the city's."""
    buf = C.frame(camx, camz)
    for r, row in enumerate(T.band(t)):
        at = (T.TOP + r) * STRIDE
        buf[at:at + STRIDE] = row
    for y, (by, kind) in enumerate(J.rows(J.lean(J.pilot(), pose - 1))):
        base = (Y + y) * STRIDE + X // 2
        for i, b in enumerate(by):
            if kind[i] == 1:
                buf[base + i] = b
            elif kind[i] == 2:                  # the pilot's left pixel
                buf[base + i] = b | (buf[base + i] & 0x0F)
            elif kind[i] == 3:                  # and its right one
                buf[base + i] = b | (buf[base + i] & 0xF0)
    return buf
