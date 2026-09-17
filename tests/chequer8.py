#!/usr/bin/env python3
"""A model of chequer8: board, desert, pilot - all of it, every frame.

The order is the order the Z80 draws in: the board from row 115 down,
the desert's two layers over the 32 rows above it, and the pilot over
the top of both.

THE VIEWPORT IS CHEQUER8'S OWN. chequer5's camera puts the horizon at
row 96 and the board over half the screen; this one puts it at 114 and
the camera 308 world units up rather than 380, which gives the board the
bottom 40% and still 64 pixels to a square at the bottom of it. The
environment carries that, so it has to be set before anything imports
the geometry - which is why this module sets it above its own imports,
and why a process that renders chequer7 cannot also render chequer8.

Nothing here is drawn once per buffer, which is the difference from
chequer6 and chequer7 and the reason this model is simpler than
theirs: there is no state to carry, so a frame is a function of the
camera, the two layer offsets and the pose.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HARRIER_MINP"] = "1"        # chequer8's viewport, which is
os.environ["HARRIER_HZ"] = "114"        # its own: the horizon at row 114
os.environ["HARRIER_CAMH"] = "308"      # puts the board in the bottom 40%

import chequer4 as C
import desert as D
import jetpack as J
from mkjetdata import X, Y

assert C.TOP == 115 and D.TOP + D.ROWS == C.TOP, \
    "the viewport and the band must meet: TOP %d, band %d..%d" \
    % (C.TOP, D.TOP, D.TOP + D.ROWS)

W, H, STRIDE, TOP, PTAB = C.W, C.H, C.STRIDE, C.TOP, C.PTAB


def frame(camx, camz, pose=1):
    """pose 0 banks left, 1 is level, 2 banks right.

    The desert's two offsets come from camx, the same camera the board
    is drawn from - which is the whole of what ties them together.
    """
    buf = C.frame(camx, camz)
    for r, row in enumerate(D.band(*D.offsets(camx))):
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
