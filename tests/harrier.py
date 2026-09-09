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
W, H, STRIDE = 256, 192, 128
HZ = 96                         # the horizon, and the last sky row
S = 256                         # a chequer square, world units
FOCAL = 221
CAMH = 380
MINP = 8                        # narrowest square drawn, in pixels
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


def frame(camx, camz):
    """The screen, and the parity the copper flips the palette by."""
    buf = bytearray(b"\x11" * (STRIDE * H))
    for y in range(HZ + 1, TOP):
        buf[y * STRIDE:(y + 1) * STRIDE] = bytes([HAZE * 0x11]) * STRIDE
    par = [0] * H
    for y in range(HZ + 1, H):
        par[y] = ((ZTAB[y] + camz) >> 8) & 1
        p = PTAB[y]
        if p:
            buf[y * STRIDE:(y + 1) * STRIDE] = line(p, ((camx % S) * p) // S)
    return buf, par
