#!/usr/bin/env python3
"""A model of zarch.z80s - Zarch's ground, flat, turning under you.

    python3 tests/zarch.py [out.gif]

The camera looks down at a fixed pitch and turns (yaw). The ground is a
chequered grid of cells, and the whole trick is this:

    A SCREEN ROW IS ONE DEPTH, whatever the yaw, because the camera does
    not roll. So the ground line a row looks at is straight and level,
    and a family of parallel grid lines crosses it at EVEN INTERVALS -
    which project to even intervals on the row, because at one depth the
    projection is linear.

So each of the two families of grid lines gives, on every row, an
arithmetic progression of crossings: a position and a step. Two
progressions merged in descending order are the row's spans, and the
chequer's colour flips at every crossing of either family, so the merge
does not even have to remember which family a crossing came from.

Everything below is integer, in 8.8 pixels, and is what the Z80 does
instruction for instruction - it is the specification, not a preview.
"""
import math
import os
import sys

W, H, STRIDE = 256, 192, 128
HZ = 96                         # the horizon, and the last sky row
FOCAL = 221
CAMH = 560                      # the camera's height over the ground
S = 256                         # a cell, world units
TOP = 136                       # first row with a grid on it
NYAW = 256                      # yaw steps, over YAW0..YAW1 degrees
YAW0, YAW1 = 10.0, 80.0
R0 = TOP - HZ

SKY, HAZE = 1, 2                # colour indices: sky, haze,
DARK = 4                        # and pairs the ground alternates, two
SHADES = 5                      # indices a shade band


def push(px):
    """Pixels to the unit everything here counts in.

    A PUSH is two bytes, which is four pixels, and a span is PUSHes -
    so positions are 8.8 fixed point in PUSHes. That is not only what
    the arithmetic wants: it is also what keeps a step inside 16 bits
    when a family of lines is nearly edge on and its spacing runs to a
    thousand pixels.
    """
    return px / 4.0


def tables():
    """Per yaw: the two families' step per row per cell, and where the
    lines they radiate from cross the horizon."""
    out = []
    for i in range(NYAW):
        phi = math.radians(YAW0 + (YAW1 - YAW0) * i / (NYAW - 1))
        out.append((round(64 * S / (CAMH * math.cos(phi))),
                    round(64 * S / (CAMH * math.sin(phi))),
                    round(64 * (128 - FOCAL * math.tan(phi))),
                    round(64 * (128 + FOCAL / math.tan(phi)))))
    return out


YAW = tables()


def setup(alpha, vp, cam):
    """One family, at row TOP: its rightmost visible line, that line's
    step down the screen, the spacing, and which colour is to its right.

    The line through the camera's own cell corner is the one whose
    position is easy - its slope is the camera's offset inside a cell -
    and walking out from it to the edge of the screen is a dozen adds.
    """
    d = -((cam & 255) * alpha >> 8)     # the j = 0 line's step per row
    pos = vp + R0 * d                   # and where it is at row TOP
    step = R0 * alpha
    par = 0
    while pos + step < (64 << 8):       # out to the right hand edge
        pos += step
        d += alpha
        par ^= 1
    while pos >= (64 << 8):             # or back in from beyond it
        pos -= step
        d -= alpha
        par ^= 1
    return pos, d, step, par


def colours(y):
    """The two the chequer alternates at this row's distance.

    Band 0 is the far end, where the ground is nearly the colour of the
    haze it meets, and the last band is under the camera's nose.
    """
    shade = (y - TOP) * SHADES // (H - TOP)
    return DARK + shade * 2, DARK + 1 + shade * 2


def palette():
    """What the demo shows those indices as: sky, haze, and the bands."""
    def mix(t, a, b):
        return tuple(max(0, min(255, int(x + (y - x) * t)))
                     for x, y in zip(a, b))
    pal = {SKY: (90, 140, 220), HAZE: (150, 190, 225)}
    for i in range(SHADES):
        t = i / (SHADES - 1.0)
        pal[DARK + 2 * i] = mix(t, (110, 160, 130), (16, 78, 28))
        pal[DARK + 1 + 2 * i] = mix(t, (132, 182, 148), (52, 128, 52))
    return pal


def frame(camx, camz, yaw):
    """The screen, and the spans it was drawn from."""
    aA, aB, vA, vB = YAW[yaw & (NYAW - 1)]
    pA, dA, sA, parA = setup(aA, vA, camx)
    pB, dB, sB, parB = setup(aB, vB, camz)
    # the cell the camera is standing in is a parity of its own, exactly
    # as it is in chequer: cross one and the two colours change places
    parA ^= (camx >> 8) & 1
    parB ^= (camz >> 8) & 1
    buf = bytearray([SKY * 0x11]) * (STRIDE * H)
    for y in range(HZ + 1, TOP):
        buf[y * STRIDE:(y + 1) * STRIDE] = bytes([HAZE * 0x11]) * STRIDE
    rows = []
    for y in range(TOP, H):
        if y > TOP:                     # on down the screen a row
            pA += dA
            sA += aA
            pB += dB
            sB += aB
            # a line can come on from the right as well as go off it:
            # when a family's lines radiate from a point off the right
            # hand edge, they all walk left as the rows go down
            while pA + sA < (64 << 8):
                pA += sA
                dA += aA
                parA ^= 1
            while pA >= (64 << 8):
                pA -= sA
                dA -= aA
                parA ^= 1
            while pB + sB < (64 << 8):
                pB += sB
                dB += aB
                parB ^= 1
            while pB >= (64 << 8):
                pB -= sB
                dB -= aB
                parB ^= 1
        rows.append(line(buf, y, pA, sA, pB, sB, parA ^ parB))
    return buf, rows


def line(buf, y, a, sa, b, sb, par):
    """One row: the two progressions merged, right to left."""
    col = colours(y)
    out, x = [], STRIDE // 2                    # in PUSHes, right to left
    a = 0 if a < 0 else a           # a family with nothing on this row
    b = 0 if b < 0 else b           # sits where it can never win
    while x > 0:
        if a > b:
            nx, a = a, a - sa
        else:
            nx, b = b, b - sb
        nx = 0 if nx < 0 else (nx >> 8)         # 8.8 PUSHes to a PUSH
        c = col[par] * 0x11
        for i in range(nx * 2, x * 2):
            buf[y * STRIDE + i] = c
        out.append((x - nx, col[par]))
        par ^= 1
        x = nx
    return out
