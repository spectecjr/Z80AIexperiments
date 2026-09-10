#!/usr/bin/env python3
"""A model of chequer2.z80s - the Space Harrier floor, exact phase.

chequer.z80s draws a scanline as one compiled run of PUSHes, which is
one dispatch a scanline however many squares it holds - but a PUSH is
four pixels, so the phase quantises to four pixels and the board steps
sideways in jumps.

This keeps the one dispatch and loses the quantising, by compiling four
runs per square width instead of one: t = 0, 1, 2 and 3 pixels. Where a
boundary lands inside a PUSH, that PUSH carries a pair with a pixel of
each colour in the right place - so a run pushes one of four registers
rather than one of two, and all four are one-byte pushes: BC, DE, HL
and AF.

The square's width is still a whole number of PUSHes. That is the part
the eye does not see; the phase is the part it does.
"""
W, H, STRIDE = 256, 192, 128
HZ = 96
S = 256
FOCAL = 221
CAMH = 380
MINP = 4
QP = 4                          # a square is a whole number of PUSHes


def ztab():
    return [0] * (HZ + 1) + [(CAMH * FOCAL) // (y - HZ)
                             for y in range(HZ + 1, H)]


def ptab():
    t = [0] * H
    for y in range(HZ + 1, H):
        p = int(round((S * (y - HZ)) / CAMH / QP)) * QP
        t[y] = p if p >= MINP else 0
    return t


ZTAB = ztab()
PTAB = ptab()
PERIODS = sorted(set(p for p in PTAB if p))


def entry(p, camx):
    """Which PUSH of which run: (offset in PUSHes, phase in pixels)."""
    i = p // 4
    prod = (camx % S) * i
    g = prod >> 8                       # the phase in whole PUSHes
    t = (prod >> 6) & 3                 # and the pixels inside one
    k = (i - 32) % (2 * i) - g
    return (k + 2 * i if k < 0 else k), t


def pattern(p, t):
    """The run for a square p wide at phase t: four pixels a PUSH.

    Entered k from its head, PUSH j covers the four pixels whose
    (x - 128 + phi) are 4*(i - j - 1) + t and the three after it - the
    k and the phase cancel, which is why one run serves every camera
    position that shares a t.
    """
    i = p // 4
    return [[1 + ((((4 * (i - j - 1) + t + q) // p)) & 1) for q in range(4)]
            for j in range(64 + 2 * i)]


def line(p, k, t):
    """One scanline as 128 MODE 4 bytes."""
    pat = pattern(p, t)
    out = bytearray(STRIDE)
    for m in range(64):
        px = pat[k + m]
        out[126 - 2 * m] = (px[0] << 4) | px[1]
        out[127 - 2 * m] = (px[2] << 4) | px[3]
    return out


def frame(camx, camz):
    """The screen, and the parity the copper flips the palette by."""
    buf = bytearray(b"\x11" * (STRIDE * H))
    par = [0] * H
    for y in range(HZ + 1, H):
        # the camera's own square is a parity too: crossing one
        # exchanges the two colours, exactly as a square of depth does,
        # and only the low byte of camx survives into the phase
        par[y] = (((ZTAB[y] + camz) >> 8) & 1) ^ ((camx >> 8) & 1)
        p = PTAB[y]
        if p:
            k, t = entry(p, camx)
            buf[y * STRIDE:(y + 1) * STRIDE] = line(p, k, t)
    return buf, par
