#!/usr/bin/env python3
"""A model of twist.z80s - a rotating ribbon, in Python.

A square cross-section turning about a vertical axis, with the angle
stepping down the screen so it twists. Every scanline is three or four
horizontal runs of one colour, which is the one thing a Z80 with a
row-major screen is good at: a run goes at 5.5 T-states a byte off the
stack pointer.

The shape only has 64 distinct silhouettes, because a square looks the
same every quarter turn - what changes is which face is which, and so
what shade each is. So the runs are compiled once per silhouette and
the shades come from a table indexed by the whole angle.
"""
import math

W, H, STRIDE = 256, 192, 128
BX = 32                         # first byte of the band the ribbon is in
BW = 64                         # and how many bytes wide it is
R = 58.0                        # half diagonal of the square, in pixels
LIGHT = 0.9                     # where the light is, radians
SHADES = 8                      # ramp of eight, palette 8..15
BG = 1                          # backdrop colour index


def geom(a):
    """(left edge, split, right edge) in pixels, and the two shades."""
    th = 2 * math.pi * a / 256
    cor = [(R * math.cos(th + k * math.pi / 2 + math.pi / 4),
            R * math.sin(th + k * math.pi / 2 + math.pi / 4))
           for k in range(4)]
    f = max(range(4), key=lambda k: cor[k][1])      # the nearest corner
    # corners run anticlockwise, so the next one round is to the left
    xl = cor[(f + 1) % 4][0]
    xs = cor[f][0]
    xr = cor[(f - 1) % 4][0]
    # the face between corners k and k+1 has its normal half way along;
    # face f is the left one, face f-1 the right
    sh = []
    for k in (f, (f - 1) % 4):
        n = th + k * math.pi / 2 + math.pi / 2
        s = max(0.0, math.cos(n - LIGHT))
        sh.append(8 + min(SHADES - 1, int(1 + s * (SHADES - 1.5))))
    return xl, xs, xr, sh[0], sh[1]


def pushes(a):
    """The 32 PUSHes of a scanline at angle a, as colour slots.

    0 is the backdrop, 1 the left face, 2 the right face. A PUSH is two
    bytes - four pixels - so that is the resolution of the edges.
    """
    xl, xs, xr, _, _ = geom(a)
    mid = W // 2
    out = []
    for m in range(32):                     # rightmost PUSH first
        x = 2 * (BX + BW - 2 - 2 * m) - mid  # its left pixel, from centre
        if x < xl - 2 or x >= xr - 2:
            out.append(0)
        elif x < xs - 2:
            out.append(1)
        else:
            out.append(2)
    return out


SHAPE = [int(round(3 * i + 52 * math.sin(2 * math.pi * i / 256)
                   + 21 * math.sin(2 * math.pi * i * 3 / 256)
                   + 9 * math.sin(2 * math.pi * i * 7 / 256))) & 255
         for i in range(256)] * 2
"""The twist down the ribbon: a steady turn with three waves running
along it. Two copies, so 192 scanlines can start anywhere in it and
read straight off the end without wrapping. Scrolling the start sends
the waves travelling down the ribbon; the rotation turns the lot."""


def frame(shift, rot):
    """The band, one scanline at a time.

    The backdrop is colour index 1 whatever row it is on, and the
    palette gives that index its own colour per scanline - the same
    trick chequer.z80s uses, and it saves reading a gradient table in
    the inner loop.
    """
    buf = bytearray(STRIDE * H)
    for y in range(H):
        a = (SHAPE[shift + y] + rot) & 255
        _, _, _, sl, sr = geom(a & 255)
        col = [BG * 0x11, sl * 0x11, sr * 0x11]
        p = pushes(a & 63)
        for m in range(32):
            v = col[p[m]]
            buf[y * STRIDE + BX + BW - 2 - 2 * m] = v
            buf[y * STRIDE + BX + BW - 1 - 2 * m] = v
    return buf
