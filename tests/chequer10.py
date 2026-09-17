#!/usr/bin/env python3
"""A model of chequer10: the board, the desert, three trees and the pilot.

chequer9's picture with scenery standing on the board: three trees,
each compiled at the eight sizes tree.py draws it at and popping from
one to the next as it comes in, which is what the arcade does - so
placing one is a matter of working out its depth, taking the size
nearest the height perspective asks for, and putting it on the row
whose depth matches.

THEY ARE DRAWN FURTHEST FIRST, which is all the depth sorting three
objects on a plane need: the caller plants them at staggered depths and
keeps the slots in that order, and a nearer tree paints over a further
one for nothing.

WHICH ROW IS ITS OWN QUESTION at a moving horizon, because a shallow
board is the deep one with scanlines left out: the depths on the screen
are a subset of the deep board's, so the tree stands on the drawn row
whose depth is nearest its own rather than on a row computed from it.
That is also what keeps it still relative to the ground when the
horizon moves - it lands on the same piece of ground either way.

AND IT IS NEVER CLIPPED. A sprite compiled as a walk of SP has no idea
where the screen ends, so a tree whose box would fall off it is not
drawn at all - which is how it leaves: it grows until the box no longer
fits and then it is gone, one frame after it has filled the bottom of
the screen.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["DESERT_PAL"] = "board4"     # chequer9's settings, whole: the
os.environ["CHQ_SWAP"] = "0xBB"         # board and its bank are the same
os.environ["JET_PAL"] = "board4"        # ones
os.environ["JET_W"] = "24"
os.environ["JET_H"] = "48"
os.environ["HARRIER_SKY"] = "15"
os.environ["DESERT_SKY"] = "15"
os.environ["HARRIER_MINP"] = "1"
os.environ["HARRIER_HZ"] = "95"
os.environ["HARRIER_CAMH"] = "308"
os.environ["DESERT_ROWS"] = "20"
ROWS0, ROWS1 = 19, 96

import chequer4 as C
import desert as D
import harrier as HR
import jetpack as J
import tree as T

W, H, STRIDE = C.W, C.H, C.STRIDE
SLOTS = 3                       # how many trees stand on the board at
                                # once, which is what the Z80 has room for
                                # in its frame as much as in its cells
TREEH = 433                     # how tall a tree is in world units: 1.7
                                # squares, which fills the screen at the
                                # depth where the board's squares are 80
                                # pixels wide

HORIZONS = list(range(ROWS1, ROWS0 - 1, -1))    # tallest board first


def depths(hz):
    """The depth of each row of the screen the board covers, as drawn.

    A shallow board leaves scanlines of the deep one out, so this is
    the same walk of the deep board the Z80 makes - and the depths on
    the screen are whichever of the deep board's it lands on.
    """
    rows = HORIZONS[hz]
    out = {}
    for r, i in enumerate(HR.lines(rows)):
        out[H - rows + r] = HR.ZTAB[HR.HZ + 1 + i]
    return out


def place(hz, camx, camz, x, z):
    """Where a tree at world (x, z) goes: (size, left byte, base row).

    None if it cannot be drawn - too far to be worth a sprite, or too
    near for its box to fit on the screen.
    """
    d = z - camz
    if d <= 0:
        return None
    rows = depths(hz)
    at = min(rows, key=lambda y: abs(rows[y] - d))
    if abs(rows[at] - d) > rows[at] * 0.5:      # off the top of the board
        return None
    px = TREEH * HR.FOCAL / d                   # what perspective asks for,
    k = min(range(len(T.SIZES)),                # and the size nearest it
            key=lambda i: abs(T.SIZES[i] - px))
    h = T.SIZES[k]
    w = T.width(h) // 2                         # in bytes, and its left one
    left = int(round((W / 2 + (x - camx) * HR.FOCAL / d - T.width(h) / 2) / 2))
    if left < 0 or left + w > STRIDE:           # it is never clipped, so a
        return None                             # box that would not fit is
    if at - h + 1 < 0 or at > H - 1:            # not drawn
        return None
    return k, left, at


def blit(buf, rows, x, y):
    """A compiled sprite's rows, as the walk of SP would leave them."""
    for j, (by, kind) in enumerate(rows):
        base = (y + j) * STRIDE + x
        for i, b in enumerate(by):
            if kind[i] == 1:
                buf[base + i] = b
            elif kind[i] == 2:                  # the left pixel only
                buf[base + i] = b | (buf[base + i] & 0x0F)
            elif kind[i] == 3:                  # and the right one
                buf[base + i] = b | (buf[base + i] & 0xF0)


def frame(camx, camz, hz=0, px=56, py=48, pose=1, trees=()):
    """hz is an index into HORIZONS: 0 is the tallest board.

    trees is up to SLOTS (size, left byte, row it stands on), FURTHEST
    FIRST - they are drawn in that order, so a nearer one paints over a
    further one. A size of TREE_N or more is no tree. The pilot is drawn
    over the lot.
    """
    rows = HORIZONS[hz]
    buf = C.frame(camx, camz, 191 - rows)
    top = H - rows - D.ROWS
    for r, row in enumerate(D.band(*D.offsets(camx))):
        at = (top + r) * STRIDE
        buf[at:at + STRIDE] = row
    for tk, tx, ty in trees:
        if tk < len(T.SIZES):
            h = T.SIZES[tk]
            blit(buf, T.rows(T.tree(h)[0]), tx, ty - h + 1)
    blit(buf, J.rows(J.lean(J.pilot(), pose - 1)), px, py)
    return buf
