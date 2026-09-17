#!/usr/bin/env python3
"""A model of chequer8: board, desert, pilot - all of it, every frame.

The order is the order the Z80 draws in: chequer5's board from row 97
down, the desert's two layers over the 24 rows above it, and the pilot
over the top of both.

Nothing here is drawn once per buffer, which is the difference from
chequer6 and chequer7 and the reason this model is simpler than
theirs: there is no state to carry, so a frame is a function of the
camera, the two layer offsets and the pose.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HARRIER_MINP"] = "1"

import chequer4 as C
import desert as D
import jetpack as J
from mkjetdata import X, Y

W, H, STRIDE, TOP, PTAB = C.W, C.H, C.STRIDE, C.TOP, C.PTAB


def frame(camx, camz, t, pose=1):
    """pose 0 banks left, 1 is level, 2 banks right; t is the desert's.

    The rear layer moves a pixel every three frames and the front one a
    pixel a frame, which is what the two offsets are.
    """
    buf = C.frame(camx, camz)
    for r, row in enumerate(D.band(t)):
        at = (D.TOP + r) * STRIDE
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
