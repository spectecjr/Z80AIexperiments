#!/usr/bin/env python3
"""A compiled sprite chain: 64x80 down to 8x10, and what it costs.

The model and the code generator behind `test_mipsprite.py`. Nothing
here runs on the Z80 - it *writes* the Z80, one straight-line block a
source row, and builds the picture those blocks are supposed to leave
so the emulator's memory can be checked against it.

MODE 4: two pixels a byte, high nibble left, 128 bytes a scanline.

    python3 tests/mipsprite.py            # the chain, sizes and stats
    python3 tests/mipsprite.py art.png    # look at the levels, 4x
"""
import sys
from collections import Counter

W, H = 64, 80                   # the master, in pixels
STRIDE = 128                    # bytes a screen line
CLEAR = -1

# MODE 4 indices. The outline owns 0, as chequer6's pilot does.
BLACK = 0
BACKDROP = 0x11                 # what the box carries where the sprite does not
HULL_D, HULL_M, HULL_L = 4, 5, 6
CANOPY, CANOPY_L = 8, 9
ENGINE, FLAME, CORE = 10, 12, 13
TRIM, SHADOW = 11, 14

# byte widths of the chain, and the height each one is drawn at when the
# sprite is at that level's own size. Width is quantised to the level;
# height is whatever the row program asks for, up to this.
LEVELS = [32, 24, 16, 12, 8, 6, 4]


def nominal(wb):
    """The height that goes with a byte width, at the master's aspect."""
    return max(1, int(round(wb * 2 * H / W)))


# ----------------------------------------------------------------- artwork

def blank(w, h):
    return [[CLEAR] * w for _ in range(h)]


def span(px, y0, y1, l0, r0, l1, r1, colour):
    """Fill between two edges that walk down the rows, as jetpack.py does."""
    h = len(px)
    w = len(px[0])
    for y in range(max(0, y0), min(h - 1, y1) + 1):
        t = 0.0 if y1 == y0 else (y - y0) / (y1 - y0)
        l = int(round(l0 + (l1 - l0) * t))
        r = int(round(r0 + (r1 - r0) * t))
        for x in range(max(0, l), min(w - 1, r) + 1):
            px[y][x] = colour


def outline(px):
    """A black edge round everything, so no byte needs a mask."""
    h, w = len(px), len(px[0])
    out = [row[:] for row in px]
    for y in range(h):
        for x in range(w):
            if px[y][x] != CLEAR:
                continue
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1),
                           (-1, 1), (1, -1), (1, 1)):
                j, i = y + dy, x + dx
                if 0 <= j < h and 0 <= i < w and px[j][i] not in (CLEAR, BLACK):
                    out[y][x] = BLACK
                    break
    return out


def gunship():
    """A 64x80 ship, seen from above: flat panels, a canopy, two engines.

    Flat regions are the point - they are what a register cache in the
    compiled code has to hit, and real MODE 4 artwork has them.
    """
    px = blank(W, H)
    # wings
    span(px, 26, 44, 2, 61, 20, 43, HULL_D)
    span(px, 26, 38, 6, 57, 22, 41, HULL_M)
    span(px, 30, 36, 8, 24, 20, 26, TRIM)
    span(px, 30, 36, 39, 55, 37, 43, TRIM)
    # fuselage
    span(px, 4, 72, 28, 35, 22, 41, HULL_M)
    span(px, 4, 72, 30, 33, 26, 37, HULL_L)
    span(px, 4, 72, 34, 35, 38, 41, SHADOW)
    # nose
    span(px, 0, 10, 30, 33, 27, 36, HULL_L)
    # canopy
    span(px, 12, 26, 28, 35, 26, 37, CANOPY)
    span(px, 14, 22, 29, 32, 28, 33, CANOPY_L)
    # engines
    span(px, 46, 68, 18, 25, 16, 27, ENGINE)
    span(px, 46, 68, 38, 45, 36, 47, ENGINE)
    span(px, 68, 76, 18, 25, 19, 24, FLAME)
    span(px, 68, 76, 38, 45, 39, 44, FLAME)
    span(px, 70, 79, 20, 23, 21, 22, CORE)
    span(px, 70, 79, 40, 43, 41, 42, CORE)
    return outline(px)


# --------------------------------------------------------------- the chain

def downscale(px, tw, th):
    """Box filter in palette space: an output pixel is the commonest
    index under it, and transparent when most of the box is."""
    sh, sw = len(px), len(px[0])
    out = blank(tw, th)
    for y in range(th):
        y0, y1 = y * sh // th, max(y * sh // th + 1, (y + 1) * sh // th)
        for x in range(tw):
            x0, x1 = x * sw // tw, max(x * sw // tw + 1, (x + 1) * sw // tw)
            seen = Counter()
            n = 0
            for j in range(y0, y1):
                for i in range(x0, x1):
                    n += 1
                    if px[j][i] != CLEAR:
                        seen[px[j][i]] += 1
            if not seen or sum(seen.values()) * 2 < n:
                continue
            # an outline that survives is worth more than one that does not
            best = max(seen.items(), key=lambda kv: (kv[1], -kv[0]))
            out[y][x] = best[0]
    return out


def pack(px, wb):
    """Pixels to MODE 4 bytes, plus a covered flag a byte.

    A byte with one pixel covered is rounded out to a whole byte with
    the outline colour - chequer6's trick - so nothing ever needs a
    read-modify-write.
    """
    rows = []
    for line in px:
        by, cov = [], []
        for b in range(wb):
            lo, hi = line[2 * b], line[2 * b + 1]
            if lo == CLEAR and hi == CLEAR:
                by.append(0)
                cov.append(False)
                continue
            lo = BLACK if lo == CLEAR else lo
            hi = BLACK if hi == CLEAR else hi
            by.append((lo << 4) | hi)
            cov.append(True)
        rows.append((by, cov))
    return rows


def runs(cov, by):
    """Covered byte spans, each rounded out to an even length so every
    write is a whole PUSH. Growing a span writes outline black."""
    out = []
    b = 0
    n = len(cov)
    while b < n:
        if not cov[b]:
            b += 1
            continue
        s = b
        while b < n and cov[b]:
            b += 1
        e = b
        if (e - s) & 1:                 # even length, or a PUSH overruns
            if e < n:
                e += 1
            else:
                s -= 1
            for i in range(s, e):
                if not cov[i]:
                    by[i] = 0
        if out and out[-1][1] >= s:     # rounding may have joined two
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


class Level:
    def __init__(self, master, wb):
        self.wb = wb
        self.wpx = wb * 2
        self.hpx = nominal(wb)
        self.px = downscale(master, self.wpx, self.hpx)
        self.rows = pack(self.px, wb)
        self.runs = [runs(c, b) for b, c in self.rows]
        self.area = sum(e - s for r in self.runs for s, e in r)

    def opaque(self):
        """The same level with the box filled: transparent bytes become
        the background colour and every row is one full-width run.

        A sprite drawn this way needs no erase where it already was -
        only where it has just left.
        """
        other = object.__new__(Level)
        other.__dict__.update(self.__dict__)
        other.rows = [([b if c else BACKDROP for b, c in zip(by, cov)],
                       [True] * len(cov)) for by, cov in self.rows]
        other.runs = [[(0, self.wb)] for _ in self.rows]
        other.area = self.wb * self.hpx
        return other

    def pairs(self):
        """Every PUSH value the level holds, as (row, value)."""
        out = []
        for y, (by, _) in enumerate(self.rows):
            for s, e in self.runs[y]:
                for i in range(e - 2, s - 1, -2):
                    out.append((y, (by[i + 1] << 8) | by[i]))
        return out


def chain(master=None):
    master = master or gunship()
    return [Level(master, wb) for wb in LEVELS]


# ------------------------------------------------------------------ report

def main():
    ch = chain()
    print("  %-9s %-9s %6s %6s %7s %7s  %s"
          % ("level", "pixels", "bytes", "rows", "covered", "of box", "values"))
    for lv in ch:
        vals = Counter(v for _, v in lv.pairs())
        print("  %-9s %-9s %6d %6d %7d %6.0f%%  %d distinct, top %d%%"
              % ("%dx%d" % (lv.wb, lv.hpx), "%dx%d" % (lv.wpx, lv.hpx),
                 lv.wb * lv.hpx, lv.hpx, lv.area,
                 100.0 * lv.area / (lv.wb * lv.hpx), len(vals),
                 round(100 * vals.most_common(1)[0][1] / sum(vals.values()))))
    if len(sys.argv) > 1:
        write_png(sys.argv[1], ch)
        print("\n  wrote %s" % sys.argv[1])
    return 0


PAL = {BLACK: (0, 0, 0), HULL_D: (60, 60, 72), HULL_M: (120, 120, 136),
       HULL_L: (180, 180, 196), CANOPY: (24, 60, 140), CANOPY_L: (96, 160, 230),
       ENGINE: (72, 64, 56), TRIM: (200, 150, 40), FLAME: (220, 90, 20),
       CORE: (255, 220, 120), SHADOW: (40, 40, 50)}


def write_png(path, ch, zoom=4):
    """The levels side by side, so the downscale can be looked at."""
    import struct
    import zlib
    gap = 4
    w = sum(lv.wpx for lv in ch) + gap * (len(ch) + 1)
    h = max(lv.hpx for lv in ch) + gap * 2
    img = [[(20, 20, 24)] * w for _ in range(h)]
    x0 = gap
    for lv in ch:
        for y, line in enumerate(lv.px):
            for x, v in enumerate(line):
                if v != CLEAR:
                    img[gap + y][x0 + x] = PAL.get(v, (255, 0, 255))
        x0 += lv.wpx + gap
    raw = b""
    for row in img:
        raw += b"\0" + bytes(c for px in row for _ in range(zoom) for c in px)
        raw *= 1
    body = b""
    for row in img:
        line = bytes(c for px in row for _ in range(zoom) for c in px)
        body += (b"\0" + line) * zoom

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w * zoom, h * zoom, 8, 2,
                                      0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(body, 9))
    png += chunk(b"IEND", b"")
    open(path, "wb").write(png)


if __name__ == "__main__":
    sys.exit(main())
