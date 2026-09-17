#!/usr/bin/env python3
"""A model of harrier.z80s - the Space Harrier floor at pixel accuracy.

chequer.z80s draws the same board with a square's width and phase
quantised to four pixels, because a scanline is one compiled run of
PUSHes and a PUSH is four pixels. This one puts every boundary on its
exact pixel instead, which costs a dispatch per square rather than per
scanline, and a byte carrying a pixel of each colour wherever a
boundary lands mid-byte.

The depth stripes are still the palette's job, exactly as before.
Below MINP, where a square is too narrow to draw honestly, the board
gives way to a haze - which is what distance does to it anyway.
"""
import os

W, H, STRIDE = 256, 192, 128
S = 256                         # a chequer square, world units
FOCAL = 221

# The viewport is three numbers, and all three come from the environment
# so that a demo can have one of its own without a second copy of this
# file. HZ decides how much of the screen the board gets - it is the
# horizon and the last sky row, so the board is the H - HZ - 1 rows
# below it - and CAMH, the camera's height in world units, decides how
# wide a square is down there. chequer8 uses 114 and 308: the board is
# the bottom 40% of the screen and still 64 pixels a square at the
# bottom of it.
HZ = int(os.environ.get("HARRIER_HZ", 96))
CAMH = int(os.environ.get("HARRIER_CAMH", 380))
MINP = int(os.environ.get("HARRIER_MINP", 8))    # narrowest square
                                # drawn, in pixels: 8 leaves haze above
                                # the board, 1 takes it to the horizon
HAZE = 3                        # the colour index the far field gets


def ztab():
    return [0] * (HZ + 1) + [(CAMH * FOCAL) // (y - HZ)
                             for y in range(HZ + 1, H)]


def ptab():
    """A square's width at each scanline, in exact pixels."""
    t = [0] * H
    for y in range(HZ + 1, H):
        p = int(round((S * (y - HZ)) / CAMH))
        t[y] = p if p >= MINP else 0
    return t


ZTAB = ztab()
PTAB = ptab()
TOP = min(y for y in range(H) if PTAB[y])       # first row with a board


def viewport(hz):
    """The same two tables for a horizon at another row.

    A square's width and a scanline's depth both depend on the row's
    distance from the horizon and on nothing else, so moving the
    horizon does not change the board - it changes how much of it is on
    the screen. This is what a demo with a horizon that moves asks for,
    and what lets one run bank serve all of them.
    """
    z = [0] * (hz + 1) + [(CAMH * FOCAL) // (y - hz) for y in range(hz + 1, H)]
    p = [0] * H
    for y in range(hz + 1, H):
        w = int(round((S * (y - hz)) / CAMH))
        p[y] = w if w >= MINP else 0
    return p, z, min(y for y in range(H) if p[y])


def line(p, phi):
    """One scanline, exactly: colour is floor((x - 128 + phi) / p)."""
    out = bytearray(STRIDE)
    for x in range(W):
        c = 1 + (((x - 128 + phi) // p) & 1)
        if x & 1:
            out[x >> 1] |= c
        else:
            out[x >> 1] = c << 4
    return out


def frame(camx, camz, hz=None):
    """The screen, and the parity the copper flips the palette by.

    hz moves the horizon, for the demos that have one that moves; the
    tables then come from viewport() above and nothing else changes.
    """
    ptab, ztab, top = (PTAB, ZTAB, TOP) if hz is None else viewport(hz)
    hz = HZ if hz is None else hz
    buf = bytearray(b"\x11" * (STRIDE * H))
    for y in range(hz + 1, top):
        buf[y * STRIDE:(y + 1) * STRIDE] = bytes([HAZE * 0x11]) * STRIDE
    par = [0] * H
    for y in range(hz + 1, H):
        # the camera's own square is a parity too: crossing one
        # exchanges the two colours, exactly as a square of depth does,
        # and only the low byte of camx survives into the phase
        par[y] = (((ztab[y] + camz) >> 8) & 1) ^ ((camx >> 8) & 1)
        p = ptab[y]
        if p:
            buf[y * STRIDE:(y + 1) * STRIDE] = line(p, ((camx % S) * p) // S)
    return buf, par
