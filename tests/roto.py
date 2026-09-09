#!/usr/bin/env python3
"""A model of roto.z80s - a rotating, zooming texture, in Python.

The texture is 16 by 16 and page aligned, so a texel's address is one
byte: the row in the top nibble, the column in the bottom. u and v are
8.8 and both wrap at 16, which is two masks.

One texel a screen byte - two pixels wide, as everywhere else here -
and the window is small, because an arbitrary computed byte is the
dearest thing this machine does.
"""
W, H, STRIDE = 256, 192, 128
BX, BW = 32, 64                 # the window, in bytes
BY, BH = 64, 64                 # and in scanlines


def frame(ur, vr, du, dv, dux, dvx, tex):
    """ur, vr: u and v at the right hand end of the first row, 8.8.

    du, dv step one byte leftwards; dux, dvx step one row down.
    """
    buf = bytearray(STRIDE * H)
    for y in range(BH):
        u, v = ur & 0xFFFF, vr & 0xFFFF
        for x in range(BW):
            u = (u + du) & 0xFFFF       # the step comes first, because
            v = (v + dv) & 0xFFFF       # the inner loop adds before it
            a = ((v >> 8) & 0xF0) | ((u >> 8) & 0x0F)   # samples
            buf[(BY + y) * STRIDE + BX + BW - 1 - x] = tex[a]
        ur = (ur + dux) & 0xFFFF
        vr = (vr + dvx) & 0xFFFF
    return buf
