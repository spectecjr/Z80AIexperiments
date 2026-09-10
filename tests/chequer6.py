#!/usr/bin/env python3
"""A model of chequer6: chequer5's board with the pilot over the top.

The board is chequer4's routine over chequer5's viewport, so the model
of it is chequer4's with HARRIER_MINP=1 - and the pilot is simply
stamped over the result, every byte of it, because that is what the Z80
does too. The only thing worth stating is that it is stamped over BOTH
halves: the rows above the board are drawn once into each buffer at
init and never touched again, so by the time a frame comes back they
are there just the same.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HARRIER_MINP"] = "1"

import chequer4 as C
import jetpack as J
from mkjetdata import X, Y

W, H, STRIDE, TOP, PTAB = C.W, C.H, C.STRIDE, C.TOP, C.PTAB


def frame(camx, camz):
    buf = C.frame(camx, camz)
    for y, (by, on) in enumerate(J.rows(J.pilot())):
        base = (Y + y) * STRIDE + X // 2
        for i, b in enumerate(by):
            if on[i]:
                buf[base + i] = b
    return buf
