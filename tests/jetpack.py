#!/usr/bin/env python3
"""The pilot: a person in a jetpack, seen from behind.

    python3 tests/jetpack.py [out.png]

The figure is built out of profiles - a list of (row, left, right) that
the rows between interpolate - because that is the only way to draw a
person into a 32 pixel wide grid and still be able to move a shoulder
by two pixels afterwards.

AND BECAUSE THEY ARE PROFILES, HE HAS A SIZE. The figure is drawn in
the 32x96 grid its numbers were tuned in and the profiles are scaled
into whatever W and H say on the way past, so he is redrawn at the size
asked for rather than resampled down to it - which on a sprite with a
one pixel outline and a two pixel highlight is the difference between a
smaller pilot and a broken one.

Transparent is -1. Everything else is a MODE 4 palette index, and the
board below owns 1, 2 and 3, so the pilot uses 0 and 4..14.
"""
import os
import sys

W = int(os.environ.get("JET_W", 32))            # what he is drawn at,
H = int(os.environ.get("JET_H", 96))            # which a demo chooses:
AW, AH = 32, 96                 # chequer6, 7 and 8 have him at the size
                                # he was drawn, chequer9 at 24x48
CLEAR = -1

BLACK, SUIT_D, SUIT_M, SUIT_L = 0, 4, 5, 6
SKIN, HELM = 7, 8
MET_L, FLAME, CORE, SHINE = 11, 12, 13, 14
if os.environ.get("JET_PAL") == "board4":
    MET_D = HELM_D = 3          # a board in four colours wants 9 and 10
    CORE = FLAME                # for the pair it draws its odd rows of
    SHINE = HELM                # squares in, and the desert wants 13 and
else:                           # 14 for a lit face and a shadow of its
    MET_D, HELM_D = 10, 9       # own. Sixteen colours is sixteen
                                # colours, so the pilot pays: his two
                                # dark greys are one grey at 3, the
                                # flame's bright core is the flame, and
                                # the white highlights are the helmet's
                                # own grey. Nine indices for a 24x48
                                # sprite, and about ten pixels of him
                                # know the difference


def blank():
    return [[CLEAR] * W for _ in range(H)]


def scale(prof):
    """A profile out of the grid it was drawn in and into this one.

    A span is scaled by its ends rather than its edges - (r + 1) out and
    one back - so that a four pixel arm at 32 wide is three pixels at 24
    and not two.
    """
    return [(int(round(y * H / AH)), int(round(l * W / AW)),
             int(round((r + 1) * W / AW)) - 1) for y, l, r in prof]


def profile(px, prof, colour):
    """Fill between a left and a right edge that walk down the rows."""
    prof = sorted(scale(prof))
    for (y0, l0, r0), (y1, l1, r1) in zip(prof, prof[1:]):
        for y in range(y0, y1 + 1):
            t = 0 if y1 == y0 else (y - y0) / (y1 - y0)
            l = int(round(l0 + (l1 - l0) * t))
            r = int(round(r0 + (r1 - r0) * t))
            for x in range(max(0, l), min(W - 1, r) + 1):
                px[y][x] = colour


def mirror(prof):
    return [(y, AW - 1 - r, AW - 1 - l) for y, l, r in prof]


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
    """The pilot as MODE 4 bytes, two pixels a byte, and how to draw each.

        0   nothing here: skip it
        1   both pixels covered: store it
        2   the left pixel only: keep the screen's right one
        3   the right pixel only: keep the screen's left one

    The first version of this had no 2 or 3 in it: a byte with one pixel
    covered was made solid by giving the other pixel to the outline,
    because a read, a mask and a write is three times the work of a
    store. That thickened the black outline to two pixels here and
    there. The board's bank is paged now and the frame has the room, so
    the edge lands where it should.
    """
    out = []
    for y in range(H):
        by, kind = [], []
        for x in range(0, W, 2):
            a, b = px[y][x], px[y][x + 1]
            if a < 0 and b < 0:
                by.append(0)
                kind.append(0)
            elif a >= 0 and b >= 0:
                by.append((a << 4) | b)
                kind.append(1)
            elif a >= 0:
                by.append(a << 4)
                kind.append(2)
            else:
                by.append(b)
                kind.append(3)
        out.append((by, kind))
    return out


def lean(px, way):
    """The same pilot, banking: the upper body goes over, the boots stay.

    A shear rather than three sets of profiles, which is what a sprite
    this small can carry - three pixels at the helmet, tapering to none
    at the knees.
    """
    if not way:
        return px
    out = blank()
    lift = max(1, int(round(3 * W / AW)))        # three pixels at 32 wide
    for y in range(H):
        k = way * int(round(lift * max(0.0, min(1.0,
                                               (72 - y * AH / H) / 40.0))))
        for x in range(W):
            if 0 <= x + k < W:
                out[y][x + k] = px[y][x]
    return out


# A SAM colour is two bits a gun and a bright bit the three of them
# share, so a triple whose parts are all even, or all odd, is the only
# kind that survives the trip through mkchqdata.sam unchanged.
PAL = {}
for _i, _rgb in ((HELM_D, (0, 2, 4)), (CORE, (7, 7, 1)), (SHINE, (7, 7, 7)),
                 (BLACK, (0, 0, 0)), (SUIT_D, (2, 0, 0)), (SUIT_M, (6, 0, 0)),
                 (SUIT_L, (7, 3, 3)), (SKIN, (7, 5, 3)), (MET_L, (4, 4, 4)),
                 (HELM, (6, 6, 6)), (FLAME, (7, 3, 1)), (MET_D, (2, 2, 2))):
    PAL[_i] = _rgb             # the ones that can be merged away first,
                               # so that where two share an index it is
                               # the keeper's colour they share


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
