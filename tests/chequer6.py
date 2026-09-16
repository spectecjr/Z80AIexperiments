#!/usr/bin/env python3
"""A model of chequer6: chequer5's board with the pilot over the top.

The board is chequer4's routine over chequer5's viewport, so the model
of it is chequer4's with HARRIER_MINP=1 - and the pilot is stamped over
the result, because that is what the Z80 does too. Two things about the
stamping:

  BOTH HALVES. The rows above the board are drawn once per buffer and
  the rows below every frame, but by the time a frame comes back they
  are both there, so the model draws the lot.

  A BYTE WITH ONE PIXEL COVERED keeps the board's other pixel, which is
  what the 0x60 and 0x61 ops do on the Z80.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HARRIER_MINP"] = "1"

import chequer4 as C
import jetpack as J
from mkjetdata import X, Y

W, H, STRIDE, TOP, PTAB = C.W, C.H, C.STRIDE, C.TOP, C.PTAB


def frame(camx, camz, pose=1):
    """pose 0 banks left, 1 is level, 2 banks right."""
    buf = C.frame(camx, camz)
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
