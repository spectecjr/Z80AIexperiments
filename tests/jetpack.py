#!/usr/bin/env python3
"""The pilot: a person in a jetpack, seen from behind, 32x96 pixels.

    python3 tests/jetpack.py [out.png]

The figure is built out of profiles - a list of (row, left, right) that
the rows between interpolate - because that is the only way to draw a
person into a 32 pixel wide grid and still be able to move a shoulder
by two pixels afterwards.

Transparent is -1. Everything else is a MODE 4 palette index, and the
board below owns 1, 2 and 3, so the pilot uses 0 and 4..14.
"""
import sys

W, H = 32, 96
CLEAR = -1

BLACK, SUIT_D, SUIT_M, SUIT_L = 0, 4, 5, 6
SKIN, HELM, HELM_D = 7, 8, 9
MET_D, MET_L, FLAME, CORE, SHINE = 10, 11, 12, 13, 14


def blank():
    return [[CLEAR] * W for _ in range(H)]


def profile(px, prof, colour):
    """Fill between a left and a right edge that walk down the rows."""
    prof = sorted(prof)
    for (y0, l0, r0), (y1, l1, r1) in zip(prof, prof[1:]):
        for y in range(y0, y1 + 1):
            t = 0 if y1 == y0 else (y - y0) / (y1 - y0)
            l = int(round(l0 + (l1 - l0) * t))
            r = int(round(r0 + (r1 - r0) * t))
            for x in range(max(0, l), min(W - 1, r) + 1):
                px[y][x] = colour


def mirror(prof):
    return [(y, W - 1 - r, W - 1 - l) for y, l, r in prof]


def both(px, prof, colour):
    profile(px, prof, colour)
    profile(px, mirror(prof), colour)


def outline(px):
    """A black edge all the way round, so the pilot reads against the board."""
    out = [row[:] for row in px]
    for y in range(H):
        for x in range(W):
            if px[y][x] != CLEAR:
                continue
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                j, i = y + dy, x + dx
                if 0 <= j < H and 0 <= i < W and px[j][i] not in (CLEAR, BLACK):
                    out[y][x] = BLACK
                    break
    return out


def pilot():
    px = blank()

    # arms: out of the shoulder, past the tank, glove at the bottom
    both(px, [(17, 3, 7), (30, 3, 7), (44, 1, 5)], SUIT_M)
    both(px, [(17, 3, 4), (30, 3, 4), (44, 1, 2)], SUIT_D)
    both(px, [(44, 1, 5), (51, 1, 5)], SUIT_D)
    both(px, [(45, 2, 4), (50, 2, 4)], BLACK)

    # legs, a gap between them, and boots
    both(px, [(46, 10, 14), (88, 10, 14)], SUIT_M)
    both(px, [(46, 10, 11), (88, 10, 11)], SUIT_D)
    both(px, [(88, 9, 14), (94, 9, 15)], BLACK)
    both(px, [(89, 10, 13), (93, 10, 14)], MET_D)

    # torso: shoulders, a waist, and a belt under the pack
    profile(px, [(12, 13, 18), (15, 8, 23), (18, 7, 24), (44, 8, 23),
                 (48, 10, 21)], SUIT_M)
    both(px, [(12, 13, 14), (15, 8, 10), (18, 7, 9), (44, 8, 10),
              (48, 10, 12)], SUIT_D)
    profile(px, [(41, 10, 21), (43, 10, 21)], MET_D)      # belt

    # the exhaust, before the nozzles so they sit over it
    both(px, [(48, 7, 11), (58, 8, 10), (66, 9, 9)], FLAME)
    both(px, [(48, 8, 10), (61, 9, 9)], CORE)

    # the jetpack: a box on the back and a tank either side of it
    profile(px, [(17, 12, 19), (40, 12, 19)], MET_D)
    profile(px, [(17, 12, 19), (19, 12, 19)], MET_L)
    profile(px, [(23, 14, 17), (24, 14, 17)], MET_L)
    both(px, [(14, 8, 10), (16, 7, 11), (40, 7, 11), (42, 8, 10)], MET_L)
    both(px, [(16, 8, 8), (40, 8, 8)], SHINE)
    both(px, [(16, 10, 11), (40, 10, 11)], MET_D)
    both(px, [(16, 7, 11), (17, 7, 11)], MET_D)   # the cap on top
    both(px, [(42, 7, 11), (47, 8, 10)], MET_D)   # nozzles

    # straps over the shoulders
    both(px, [(13, 11, 12), (17, 12, 13)], MET_D)

    # helmet, and the neck under it
    profile(px, [(11, 13, 18), (13, 13, 18)], SKIN)
    profile(px, [(0, 13, 18), (1, 12, 19), (3, 11, 20), (7, 11, 20),
                 (9, 12, 19), (11, 13, 18)], HELM)
    profile(px, [(7, 11, 20), (11, 13, 18)], HELM_D)
    profile(px, [(2, 12, 13), (5, 12, 13)], SHINE)
    return outline(px)


def rows(px):
    """The pilot as MODE 4 bytes, two pixels a byte, and which are drawn.

    A byte with only one of its pixels covered would need a read, a mask
    and a write to draw - three times the work of a byte that is simply
    stored - so the odd pixel goes to the outline colour instead and the
    byte becomes solid. The outline is black and one pixel wide, so what
    that does is thicken it to two pixels here and there, which is the
    cheapest possible answer to a silhouette that does not land on a byte.
    """
    out = []
    for y in range(H):
        by, on = [], []
        for x in range(0, W, 2):
            a, b = px[y][x], px[y][x + 1]
            if a < 0 and b >= 0:
                a = BLACK
            elif b < 0 and a >= 0:
                b = BLACK
            by.append(((a if a >= 0 else 0) << 4) | (b if b >= 0 else 0))
            on.append(a >= 0)
        out.append((by, on))
    return out


# A SAM colour is two bits a gun and a bright bit the three of them
# share, so a triple whose parts are all even, or all odd, is the only
# kind that survives the trip through mkchqdata.sam unchanged.
PAL = {BLACK: (0, 0, 0), SUIT_D: (2, 0, 0), SUIT_M: (6, 0, 0),
       SUIT_L: (7, 3, 3), SKIN: (7, 5, 3), HELM: (6, 6, 6),
       HELM_D: (0, 2, 4), MET_D: (2, 2, 2), MET_L: (4, 4, 4),
       FLAME: (7, 3, 1), CORE: (7, 7, 1), SHINE: (7, 7, 7)}


def main():
    from PIL import Image
    px = pilot()
    img = Image.new("RGB", (W, H), (30, 60, 120))
    for y, (by, on) in enumerate(rows(px)):
        for i, b in enumerate(by):
            if not on[i]:
                continue
            for k, c in enumerate((b >> 4, b & 15)):
                img.putpixel((2 * i + k, y), tuple(v * 255 // 7 for v in PAL[c]))
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/pilot.png"
    img.resize((W * 8, H * 8), Image.NEAREST).save(out)
    r = rows(px)
    solid = sum(1 for by, on in r for o in on if o)
    same = sum(1 for y in range(1, H) if r[y] == r[y - 1])
    print("%s: %d bytes drawn of %d, %d rows repeat the one above"
          % (out, solid, W // 2 * H, same))


if __name__ == "__main__":
    main()
