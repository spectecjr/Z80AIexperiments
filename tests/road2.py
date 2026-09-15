#!/usr/bin/env python3
"""A model of road2.z80s - the Hang On road again, at 50 Hz.

road.z80s puts everything that repeats with distance into the palette:
the mown stripes, the tarmac's bands, the kerb's red and white and the
dashes are two bits a scanline, and riding forward costs nothing in
pixels. That wants a CLUT write every scanline, which this machine
cannot afford - and which fights the fill for SP besides, because an
interrupt would push its return address into the middle of the road.

So here the palette is fixed and all of it is drawn. Two things pay
for that:

  ONLY WHAT MOVED IS REPAINTED. A row's road is one interval, so the
  window is the road plus a fixed margin either side - about twenty
  PUSHes a row rather than sixty-four. The margin has to cover what the
  road moves in the *two* frames a buffer waits its turn, which is
  eight pixels at 20 world units a frame and is what sets M. Ride
  faster and it wants more: eleven at 30, fourteen at 40.

  EXCEPT WHEN THE BAND PARITY FLIPS, which for a given row happens once
  every 512 world units of travel, so roughly one row in twelve a frame
  wants its whole width back.

The geometry is road.z80s's exactly: harrier's camera, the bend
integrated twice up the screen, and the centre held inside [w, 255-w]
so that nothing is ever clipped.

What is new besides the palette is that a marking narrower than four
pixels is drawn rather than dropped. Nothing inside the road is a span
any more: the whole of it is one compiled run a row, so both kerbs,
their inner edges and the centre line are baked to the pixel and a one
pixel line is just a nibble in a PUSHed constant.
"""
import math

W, H, STRIDE = 256, 192, 128
HZ = 96                         # the horizon, and the last sky row
FOCAL = 221                     # harrier's camera exactly
CAMH = 256                      # a world unit of camx is one row's worth
                                # of lateral step in 8.8 pixels
RW = 170                        # the road's half width, world units: 63
                                # pixels at the bottom of the screen,
                                # which is what lets the camera reach
                                # either kerb with none of it clipped
MINW = 2                        # the far end, in pixels
NSEG = 64                       # segments in the track loop
SEGSH = 9                       # 512 world units each
BANDSH = 8                      # the bands, 512 world units. A band that
                                # flips is a row repainted in full, so the
                                # period is what that costs: 256 units is
                                # one row in six a frame and 12,000
                                # T-states dearer, which is the whole
                                # difference between missing 50 Hz and
                                # making it

# The fixed palette. Everything that alternates with distance is a pair
# of indices rather than one index and a CLUT write, and bit 0 of each
# pair is the band's parity - which is why they are numbered this way.
SKY0, SKY1, SKY2, SKY3 = 12, 13, 14, 15
GRASS0, GRASS1 = 2, 3
TARMAC0, TARMAC1 = 4, 5
KERB0, KERB1 = 6, 7             # red and white
LINE = 8                        # and white again, for the dashes

# Two boundaries inside one PUSH would want a byte carrying three
# colours, which the mixed-pair table cannot hold - so no *span* may be
# narrower than this. The kerbs and the centre line are no longer spans,
# which is exactly why they may now be one pixel wide.
MINSPAN = 4


def ztab():
    return [0] * (HZ + 1) + [(CAMH * FOCAL) // (y - HZ)
                             for y in range(HZ + 1, H)]


def wtab():
    """Half the road's width at each scanline, in exact pixels."""
    return [0] * (HZ + 1) + [max(MINW, (RW * (y - HZ)) // CAMH)
                             for y in range(HZ + 1, H)]


def ktab():
    """The kerb, a sixth of the road's half width - never less than one.

    road.z80s drops it below four pixels because a kerb that narrow puts
    two boundaries in one PUSH. Here the road's edge byte is baked per
    row, so it can carry grass, kerb and tarmac at once and the kerbs
    keep their red and white all the way to the horizon.
    """
    return [max(1, w // 6) if w else 0 for w in WTAB]


def ltab():
    """The centre line's width in whole pixels, never less than one."""
    return [max(1, w // 10) if w else 0 for w in WTAB]


def clamp():
    """How far the road's centre may go, so that nothing is clipped."""
    return [(max(w, 4), min(255 - w, 251)) for w in WTAB]


ZTAB = ztab()
WTAB = wtab()
KTAB = ktab()
LTAB = ltab()
CLAMP = clamp()


def track():
    """Curvature a segment, in 1/256ths of a pixel a row squared."""
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
    """Per scanline: the band's parity and the road's centre.

    Both come out of one 16-bit add, exactly as in road.z80s. The centre
    is the double integral of the curvature at that row's depth, and the
    camera's lateral offset rides in as the constant of the first
    integration.
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
        par[y] = (z >> BANDSH) & 1
        dx = (dx + TRACK[(z >> SEGSH) % NSEG]) & 0xFFFF
        x = (x + dx) & 0xFFFF
    return par, cen


def sky():
    """Four static bands, drawn once into both buffers and never again."""
    out = []
    for y in range(HZ + 1):
        out.append([SKY0, SKY1, SKY2, SKY3][min(3, (y * 4) // (HZ + 1))])
    return out


SKY = sky()


def line(c, w, k, lw, par):
    """One scanline of road, exactly, at centre c.

    The parity picks one of each pair of colours, and the dash rides on
    it too: the centre line shows on one band and is the tarmac's own
    colour on the next. Which costs nothing - a second bit would double
    the run bank, because the line is baked into the runs.
    """
    grass, tarmac, kerb = GRASS0 + par, TARMAC0 + par, KERB0 + par
    mark = LINE if par else tarmac
    lx = c - lw // 2
    out = bytearray(STRIDE)
    for x in range(W):
        if x < c - w or x >= c + w:
            col = grass
        elif x < c - w + k or x >= c + w - k:
            col = kerb
        elif lx <= x < lx + lw:
            col = mark
        else:
            col = tarmac
        if x & 1:
            out[x >> 1] |= col
        else:
            out[x >> 1] = col << 4
    return out


def frame(camx, camz):
    """The whole screen as it should look, and the parities behind it.

    This is the *ideal* picture, not an account of what the Z80 chose to
    repaint: road2.z80s touches only what moved, and has to land here
    anyway, which is a stronger thing to test than a list of spans.
    """
    par, cen = geometry(camx, camz)
    buf = bytearray(STRIDE * H)
    for y in range(HZ + 1):
        buf[y * STRIDE:(y + 1) * STRIDE] = bytes([SKY[y] * 17]) * STRIDE
    for y in range(HZ + 1, H):
        buf[y * STRIDE:(y + 1) * STRIDE] = line(cen[y], WTAB[y], KTAB[y],
                                                LTAB[y], par[y])
    return buf, par
