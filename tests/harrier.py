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
SKY = int(os.environ.get("HARRIER_SKY", 1))     # and the sky: the board's
                                # own first colour where a copper grades
                                # the two apart by scanline, an index of
                                # its own where the palette has to sit
                                # still


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
FULL = [y for y in range(H) if PTAB[y]]         # and every row it covers,
                                                # which is the deep board a
                                                # moving horizon samples


def step(n):
    """The DDA step for a board of n scanlines, in 8.8 fixed point.

    The board is always the same picture - the deepest one the tables
    were built for - and a shallower horizon shows it with scanlines
    left out rather than squeezed, so that the square at the bottom of
    the screen is the same size whatever the horizon is doing. This is
    what steps through the deep board while the shallow one is drawn.
    """
    return int(round((len(FULL) - 1) * 256 / (n - 1)))


def lines(n):
    """Which row of the deep board each of n drawn rows shows.

    The accumulator starts at half a step so that the ends are exact:
    the top drawn row is the deep board's first and the bottom one is
    its last, whatever rounding does in between. The Z80 keeps the
    fraction in C and the row in L, so this is the same arithmetic.
    """
    d = step(n)
    return [(0x80 + j * d) >> 8 for j in range(n)]


def viewport(hz):
    """The board's two tables for a horizon at another row.

    A square's width and a scanline's depth both depend on the row's
    distance from the horizon and on nothing else, so ONE set of tables
    serves every horizon. What changes with the horizon is how many
    scanlines there are to put them on - and rather than rescale them
    into the space, which tilts the board and shrinks the squares at
    the bottom of the screen, the rows in between are dropped.
    """
    n = H - 1 - hz
    z, p = [0] * H, [0] * H
    for y, i in enumerate(lines(n), hz + 1):
        z[y] = ZTAB[HZ + 1 + i]
        p[y] = PTAB[HZ + 1 + i]
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
    buf = bytearray(bytes([SKY * 0x11]) * (STRIDE * H))
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
