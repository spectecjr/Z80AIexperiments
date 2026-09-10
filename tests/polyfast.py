#!/usr/bin/env python3
"""A model of polyfast.z80s - renderlit's rasteriser, done per scanline.

renderlit walks each of a quad's four edges with Bresenham into one of
two scanline arrays and then reads the arrays back. Measured, that is
426 T-states a scanline before anything is filled: 160 in the edge
walks (39 each plus 27 for every pixel of sideways travel), 55 to read
the arrays back through EXX and a PUSH/POP, ~120 of span setup and ~90
of loop.

polyfast keeps no arrays. Each side of the quad is a chain of edges,
walked as an 8.8 fixed point DDA in a register pair: a scanline is one
ADD HL,BC a side, eleven T-states, whatever the slope. The steps are
constant while both chains stay on the same edge, so they are patched
into the loop and the quad is drawn in one to three segments.

A DDA truncates where Bresenham rounds, so this does not put every
edge pixel where renderlit does - it is a different rasteriser, not a
faster copy. The chains start half a pixel in, which makes it round to
nearest rather than down.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raster

HALF = 0x80

# 65536/dy, to the byte, for every height a face can have. Dividing
# costs 850 T-states on a Z80 and a quarter-square multiply costs 131,
# so an edge is two multiplies against this rather than a division -
# at the price of a truncation under a 256th of a pixel a scanline.
RECIP = [0] + [65535 // dy for dy in range(1, 192)]


def edge(x0, y0, x1, y1):
    """A chain edge as (scanlines, accumulator, step), 8.8 fixed."""
    dy = y1 - y0
    dx = x1 - x0
    step = ((abs(dx) * RECIP[dy]) >> 8) & 0xFFFF
    if dx < 0:
        step = (-step) & 0xFFFF
    acc = (((x0 << 8) | HALF) - step) & 0xFFFF   # one step back
    return dy, acc, step


def chains(pts):
    """Down the screen is the right hand side, up is the left.

    A convex quad wound the way renderlit's face table gives it puts
    its descending edges in one contiguous run, so taking them in
    order - and the ascending ones turned round, in reverse order -
    gives both chains top to bottom.
    """
    right, left = [], []
    for k in range(4):
        x0, y0 = pts[k]
        x1, y1 = pts[(k + 1) & 3]
        if y1 > y0:
            right.append(edge(x0, y0, x1, y1))
    for k in (3, 2, 1, 0):
        x0, y0 = pts[k]
        x1, y1 = pts[(k + 1) & 3]
        if y1 < y0:
            left.append(edge(x1, y1, x0, y0))
    return left, right


def fill_quad(buf, pts, colour):
    ytop = min(p[1] for p in pts)
    ybot = max(p[1] for p in pts)
    if ytop == ybot:
        return
    left, right = chains(pts)
    todo = ybot - ytop
    li = ri = 0
    lrem = rrem = 0
    lacc = racc = lstep = rstep = 0
    y = ytop
    while todo:
        if not lrem:
            lrem, lacc, lstep = left[li]
            li += 1
        if not rrem:
            rrem, racc, rstep = right[ri]
            ri += 1
        n = min(lrem, rrem, todo)
        lrem -= n
        rrem -= n
        todo -= n
        for _ in range(n):
            lacc = (lacc + lstep) & 0xFFFF
            racc = (racc + rstep) & 0xFFFF
            xl, xr = lacc >> 8, racc >> 8
            if xl <= xr:
                raster.span(buf, y, xl, xr, colour)
            y += 1


FACES = raster.FACES


def render(screen_pts, colours, vis, buf=None):
    """The six faces of one prism, renderlit's dispatch order."""
    if buf is None:
        buf = bytearray(raster.STRIDE * raster.H)
    for f, idx in enumerate(FACES):
        if vis[f]:
            fill_quad(buf, [screen_pts[k] for k in idx], colours[f])
    return buf
