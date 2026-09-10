#!/usr/bin/env python3
"""A model of stars.z80s - a 3D starfield.

A star is a direction and a distance: x and y are signed bytes, z runs
from 255 down to ZMIN, and the screen position is x*64/z away from the
middle. That is transform3d's projection with the rotation taken out -
one reciprocal lookup and two 8x8 multiplies a star - which is what
makes it cheap enough to do hundreds of them.

Nothing is cleared. Each star remembers where it last put itself in
each buffer and blanks that nibble before plotting the new one, so the
cost is per star rather than per screen. Two buffers means the address
to blank is the one from two frames ago, which is why there are two
sets of them.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raster

W, H, STRIDE = raster.W, raster.H, raster.STRIDE

NSTARS = 192
ZMIN = 64                       # the reciprocal table's floor
ZMAX = 255
SPEED = 3                       # how much nearer a star gets a frame
YLIM = 95                       # half the screen, less a pixel

# 256*64/z, clamped to a byte: the same table transform3d builds, for
# the same reason. Below ZMIN it would not fit.
RECIP = [255] * 256
for z in range(ZMIN, 256):
    RECIP[z] = min(255, (256 * 64) // z)

# Eight shades of grey, nearest brightest. MODE 4's first eight are the
# white ramp renderlit uses.
RAMP = [7, 7, 6, 6, 5, 4, 3, 2]


def s8(v):
    return v - 256 if v > 127 else v


def smul(x, r):
    """(x * r) >> 8, signed in x - transform3d's own arithmetic."""
    v = (abs(x) * r) >> 8
    return -v if x < 0 else v


class Field(object):
    def __init__(self, seed=0xACE1):
        self.lfsr = seed
        self.star = []
        for _ in range(NSTARS):
            self.star.append(list(self.spawn(first=True)))
        self.old = [[None] * NSTARS, [None] * NSTARS]
        self.buf = 0

    def rnd(self):
        """A sixteen bit LFSR, taps 16, 14, 13, 11 - one byte a call."""
        for _ in range(8):
            bit = ((self.lfsr >> 0) ^ (self.lfsr >> 2) ^ (self.lfsr >> 3)
                   ^ (self.lfsr >> 5)) & 1
            self.lfsr = (self.lfsr >> 1) | (bit << 15)
        return self.lfsr & 0xFF

    def spawn(self, first=False):
        x = s8(self.rnd())
        y = s8(self.rnd())
        z = ZMIN + (self.rnd() * (ZMAX - ZMIN) >> 8) if first else ZMAX
        return x, y, z

    def frame(self, buf):
        """One frame into buf, which is the buffer of two frames ago."""
        b = self.buf
        for i in range(NSTARS):
            was = self.old[b][i]
            if was is not None:
                a, keep = was
                buf[a] &= keep
            s = self.star[i]
            s[2] -= SPEED
            if s[2] < ZMIN:
                s[0], s[1], s[2] = self.spawn()
            r = RECIP[s[2]]
            oy = smul(s[1], r)
            if oy > YLIM or oy < -YLIM:
                s[0], s[1], s[2] = self.spawn()
                r = RECIP[s[2]]
                oy = smul(s[1], r)
            ox = smul(s[0], r)
            sx = 128 + ox
            sy = 96 - oy
            a = sy * STRIDE + (sx >> 1)
            col = RAMP[s[2] >> 5]
            if sx & 1:
                buf[a] = (buf[a] & 0xF0) | col
                self.old[b][i] = (a, 0xF0)
            else:
                buf[a] = (buf[a] & 0x0F) | (col << 4)
                self.old[b][i] = (a, 0x0F)
        self.buf ^= 1
        return buf
