#!/usr/bin/env python3
"""A model of balls.z80s - vector balls on a spinning cube.

Twenty balls at a cube's eight corners and twelve edge midpoints, so
every coordinate is -S, 0 or +S. That is the whole trick: a rotated
coordinate is m0*x + m1*y + m2*z, and if x, y and z can only be those
three values then the nine products m[j]*S are worked out once a frame
and a ball's position is three signed adds. No multiply table, no
transform3d, and nine multiplies a frame rather than nine a ball.

The projection is transform3d's - 64/z from a reciprocal table, two
8x8 multiplies - and the balls are drawn back to front as rows of
whole bytes, so nothing needs a mask. Each ball remembers where it was
in each buffer and blanks that, the way stars.z80s does.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raster
from test_democube import Model

W, H, STRIDE = raster.W, raster.H, raster.STRIDE

S = 40                          # half the cube
TZ = 150                        # how far away, in the same units
ZMIN = 64
SPIN = (2, 3, 1)

RECIP = [255] * 256
for z in range(ZMIN, 256):
    RECIP[z] = min(255, (256 * 64) // z)

# A ball: rows of whole bytes, (offset, length), 8 by 6 pixels.
ROWS = [(1, 2), (0, 4), (0, 4), (0, 4), (0, 4), (1, 2)]
BH = len(ROWS)

# Four shades, nearest brightest, in both nibbles.
SHADE = [7, 6, 5, 4]


def points():
    """A cube's corners and edge midpoints, twenty of them."""
    out = []
    for x in (-1, 0, 1):
        for y in (-1, 0, 1):
            for z in (-1, 0, 1):
                if [x, y, z].count(0) <= 1 and (x, y, z) != (0, 0, 0):
                    out.append((x * S, y * S, z * S))
    return out


POINTS = points()
NBALLS = len(POINTS)


def s8(v):
    return v - 256 if v > 127 else v


def smul(x, r):
    v = (abs(x) * r) >> 8
    return -v if x < 0 else v


class Balls(Model):
    def __init__(self):
        Model.__init__(self)
        self.da = list(SPIN)
        self.old = [[None] * NBALLS, [None] * NBALLS]
        self.buf = 0

    def frame(self, buf):
        self.spin()
        m = [s8(v & 0xFF) for v in self.m]
        ms = [(abs(v) * S) >> 7 * 0 for v in m]         # placeholder
        # m is 1.7 signed, so m*S >> 7 is the rotated contribution of a
        # coordinate that is exactly S.
        ms = [(v * S) >> 7 for v in m]

        b = self.buf
        drawn = []
        for i, (px, py, pz) in enumerate(POINTS):
            sx_ = [px // S, py // S, pz // S]           # -1, 0 or +1
            rx = sum(ms[0 + k] * sx_[k] for k in range(3))
            ry = sum(ms[3 + k] * sx_[k] for k in range(3))
            rz = sum(ms[6 + k] * sx_[k] for k in range(3))
            z = TZ + rz
            drawn.append((z, i, rx, ry))
        drawn.sort(key=lambda t: -t[0])                 # farthest first

        for i in range(NBALLS):
            was = self.old[b][i]
            if was is not None:
                self.blit(buf, was, 0)
                self.old[b][i] = None
        for z, i, rx, ry in drawn:
            zc = max(ZMIN, min(255, z))
            r = RECIP[zc]
            ox, oy = smul(rx, r), smul(ry, r)
            bx = (128 + ox) >> 1
            by = 96 - oy
            if by < 0 or by + BH > H or bx < 0 or bx + 4 > STRIDE:
                continue
            col = SHADE[min(3, (zc - ZMIN) >> 5)] * 0x11
            self.blit(buf, (bx, by), col)
            self.old[b][i] = (bx, by)
        self.buf ^= 1
        return buf

    def blit(self, buf, at, col):
        bx, by = at
        for k, (off, ln) in enumerate(ROWS):
            a = (by + k) * STRIDE + bx + off
            for j in range(ln):
                buf[a + j] = col
