#!/usr/bin/env python3
"""A model of road.z80s - the Hang On road, at pixel accuracy.

chequer.z80s and harrier.z80s draw a board whose pattern is a function
of x, so a scanline is a square wave and the whole of it is one run.
A road is not: a scanline is seven spans - grass, kerb, tarmac, the
centre line, tarmac, kerb, grass - around a centre that moves with the
bend. So this one dispatches a span rather than a scanline, the way
harrier dispatches a square.

What it keeps from them is the one idea that matters. The tarmac's
bands, the kerb's red and white, the dashes down the middle and the
mown stripes in the grass are all constant along a scanline, so none
of them are drawn: they are two bits a scanline into the palette, and
riding forward costs nothing in pixels at all. Only steering and the
bend move a pixel.

The camera is harrier's, 128 units up with the horizon at row 96, and
the bend is the arcade's: curvature integrated twice up the screen,
sampled at each row's depth from a track that scrolls past underneath.
"""
import math

W, H, STRIDE = 256, 192, 128
HZ = 96                         # the horizon, and the last sky row
FOCAL = 221                     # harrier's camera exactly: 256*221 is
CAMH = 256                      # 128*442, and a world unit of camx is
                                # one row's worth of lateral step in 8.8
                                # pixels, which is what CAMH being 256
                                # buys and what makes steering an add
RW = 170                        # the road's half width, world units:
                                # 63 pixels at the bottom of the screen,
                                # which is what lets the camera reach
                                # either edge of the road without any
                                # part of it leaving the screen
MINW = 2                        # the far end is never thinner than a
                                # span, in pixels
NSEG = 64                       # segments in the track loop
SEGSH = 9                       # 512 world units each
BANDSH = 7                      # the tarmac's bands, 128 units
DASHSH = 6                      # the dashes, half that

GRASS, TARMAC, KERB, LINE = 1, 2, 3, 4

# A span narrower than four pixels can put two boundaries inside one
# PUSH, which carries a pixel of each colour and so can only hold one.
# Nothing here is allowed to be narrower: a kerb or a centre line that
# would be, is not drawn at all on that row.
MINSPAN = 4


def ztab():
    return [0] * (HZ + 1) + [(CAMH * FOCAL) // (y - HZ)
                             for y in range(HZ + 1, H)]


def wtab():
    """Half the road's width at each scanline, in exact pixels."""
    return [0] * (HZ + 1) + [max(MINW, (RW * (y - HZ)) // CAMH)
                             for y in range(HZ + 1, H)]


def ktab():
    """The kerb, a sixth of the road's half width."""
    return [w // 6 if w // 6 >= MINSPAN else 0 for w in WTAB]


def stab():
    """Half the centre line, which wants a whole span or none."""
    return [w // 20 if 2 * (w // 20) >= MINSPAN else 0 for w in WTAB]


def clamp():
    """How far the road's centre may go, so that nothing is clipped.

    A boundary off the side of the screen would want a PUSH that does
    not exist, so the centre is held inside [w, 255-w] and the road
    always fits. That is not a restriction on the camera: the road is
    126 pixels wide at the bottom of a 256 pixel screen precisely so
    that the camera can sit over either kerb and still see all of it.
    The four pixels of margin at each end keep the 8.8 accumulator
    clear of its own wrap, which dx can be 656 short of.
    """
    return [(max(w, 4), min(255 - w, 251)) for w in WTAB]


ZTAB = ztab()
WTAB = wtab()
KTAB = ktab()
STAB = stab()
CLAMP = clamp()


def track():
    """Curvature a segment, in 1/128ths of a pixel a row squared.

    Integrated twice up the screen, so the amplitude here is not the
    bend: a peak of seven is about a hundred pixels of swing at the
    horizon, which is as far as it can go without the centre reaching
    the rails that stop the road being clipped - the
    numbers are small because the double integral makes them so, and
    quantising a bend's profile to five levels is invisible after it.
    Each one eases in and out, because a step change in curvature reads
    as a kink in the road rather than as a corner.

    Sixty-four segments of 512 units is a lap of 32,768, so camz's own
    16 bits are exactly two laps and the track joins up with itself.
    """
    t = [0] * NSEG

    def bend(a, n, amp):
        for i in range(n):
            t[(a + i) % NSEG] = int(round(amp * math.sin(math.pi *
                                                         (i + 0.5) / n)))

    bend(4, 12, 5)              # an easy right
    bend(20, 8, -7)             # a tight left
    bend(32, 16, 4)             # a long right, most of a straight away
    bend(52, 9, -6)             # and a left back onto the start
    return t


TRACK = track()


def geometry(camx, camz):
    """Per scanline: the palette's two parities and the road's centre.

    Both come out of one 16-bit add. The parities are bits 6 and 7 of
    the scanline's depth, which is all forward motion costs; the centre
    is the double integral of the curvature at that depth, and the
    camera's own lateral offset rides in as the constant of the first
    integration - a camx of one world unit is one 8.8 pixel of lateral
    step a row, which is what CAMH being 256 buys.
    """
    par = [0] * H
    cen = [0] * H
    x = ((128 << 8) - camx * (H - 1 - HZ)) & 0xFFFF      # 8.8 pixels
    dx = camx & 0xFFFF
    for y in range(H - 1, HZ, -1):
        lo, hi = CLAMP[y]
        x = (min(max(x >> 8, lo), hi) << 8) | (x & 255)
        cen[y] = x >> 8
        z = (ZTAB[y] + camz) & 0xFFFF
        par[y] = ((z >> BANDSH) & 1) << 1 | ((z >> DASHSH) & 1)
        dx = (dx + TRACK[(z >> SEGSH) % NSEG]) & 0xFFFF
        x = (x + dx) & 0xFFFF
    return par, cen


def line(c, w, k, s):
    """One scanline of road, exactly, at centre c."""
    b = (c - w, c - w + k, c - s, c + s, c + w - k, c + w)
    out = bytearray(STRIDE)
    for x in range(W):
        if x < b[0] or x >= b[5]:
            col = GRASS
        elif x < b[1] or x >= b[4]:
            col = KERB
        elif x < b[2] or x >= b[3]:
            col = TARMAC
        else:
            col = LINE
        if x & 1:
            out[x >> 1] |= col
        else:
            out[x >> 1] = col << 4
    return out


def frame(camx, camz):
    """The screen, and the two parities the copper reads a scanline."""
    par, cen = geometry(camx, camz)
    buf = bytearray(b"\x11" * (STRIDE * H))
    for y in range(HZ + 1, H):
        buf[y * STRIDE:(y + 1) * STRIDE] = line(cen[y], WTAB[y],
                                                KTAB[y], STAB[y])
    return buf, par
