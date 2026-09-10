#!/usr/bin/env python3
"""A model of chequer.z80s - a Space Harrier floor, in Python.

An infinite chequerboard plane at a fixed camera height, scrolling both
ways. The depth alternation is not drawn at all: each scanline is one
fixed depth, so the row parity is constant along it and belongs to the
palette. The pixels carry only the vertical lines of the board.

Three consequences, and they are the whole design:

  - scrolling forward costs nothing in pixels. It moves the scanlines
    at which the palette flips, and nothing else.
  - scrolling sideways is a phase, and the phase as a *fraction of the
    period* is the same on every scanline - the camera sits in the same
    part of a square whatever the distance - so it is one number a
    frame, not one a scanline.
  - a scanline is a square wave, so it is one run of alternating
    PUSHes: one dispatch a scanline rather than one a square, which is
    what stops the cost exploding as the squares shrink to nothing at
    the horizon.

The colour of pixel x on a scanline whose square is p pixels wide is
floor((x - 128 + phi) / p) & 1, with phi = the camera's offset inside a
square scaled to that scanline. Filling rightwards to leftwards off the
stack pointer, the whole line follows from A = (127 + phi) mod 2p - one
byte a scanline, which indexes the compiled run.
"""
W, H, STRIDE = 256, 192, 128
HZ = 96                         # the horizon, and the last sky row
S = 256                         # a chequer square, world units
FOCAL = 221                     # half width over tan(30 degrees)
CAMH = 380                      # camera height: 64 pixels a square at the
                                # bottom row, which is 95 rows down
MINP = 4                        # narrowest square drawn, in pixels
QP = 4                          # a square is a whole number of PUSHes
QE = 4                          # and so is the phase


def ztab():
    """Depth at each floor scanline. Fixed, because the height is."""
    return [0] * (HZ + 1) + [(CAMH * FOCAL) // (y - HZ)
                             for y in range(HZ + 1, H)]


def ptab():
    """Square width at each floor scanline, in pixels. Fixed as well."""
    t = [0] * H
    for y in range(HZ + 1, H):
        p = int(round((S * (y - HZ)) / CAMH / QP)) * QP
        t[y] = p if p >= MINP else 0
    return t


ZTAB = ztab()
PTAB = ptab()
PERIODS = sorted(set(p for p in PTAB if p))


def entry(p, camx):
    """Which PUSH of the run the right hand edge starts at, 0..2i-1.

    A run's blocks start at its head; the board's boundaries are fixed
    to the middle of the screen. Lining the two up: the rightmost PUSH
    covers x = 252..255, so the colour there is
    floor((124 + phi) / p) & 1, and reading a square wave leftwards
    rather than rightwards inverts it - which is half a cycle, i
    PUSHes. That is the whole of the following.
    """
    i = p // 4
    g = ((camx % S) * i) // S           # phi >> 2, and it is under 2i
    k = (i - 32) % (2 * i) - g
    return k + 2 * i if k < 0 else k


def line(p, k):
    """One scanline as 128 MODE 4 bytes of colour index 1 and 2.

    A PUSH is the unit: two bytes, four pixels, one colour, filled
    rightwards to leftwards. The board's boundaries land on that grid
    and nowhere else, which is the whole of the quantisation.
    """
    out = bytearray(STRIDE)
    for m in range(64):
        v = pattern(p)[k + m] * 0x11
        out[126 - 2 * m] = v
        out[127 - 2 * m] = v
    return out


def pattern(p):
    """The compiled run for a square p pixels wide: one colour a PUSH.

    i PUSHes of one colour then i of the other, from the head of the
    run. 64 of them cover a scanline; the extra cycle is what an entry
    part way in spills off the left hand end, into the row above, which
    is drawn next.
    """
    i = p // 4
    return [1 + ((j // i) & 1) for j in range(64 + 2 * i)]


def frame(camx, camz):
    """The screen, and the parity the copper flips the palette by.

    Everything is colour index 1 and 2 - the sky included, which is all
    index 1 - because the palette is what says what those two mean on
    any given scanline.
    """
    buf = bytearray(b"\x11" * (STRIDE * H))
    par = [0] * H
    for y in range(HZ + 1, H):
        # the camera's own square is a parity too: crossing one
        # exchanges the two colours, exactly as a square of depth does,
        # and only the low byte of camx survives into the phase
        par[y] = (((ZTAB[y] + camz) >> 8) & 1) ^ ((camx >> 8) & 1)
        p = PTAB[y]
        if p:
            buf[y * STRIDE:(y + 1) * STRIDE] = line(p, entry(p, camx))
    return buf, par
