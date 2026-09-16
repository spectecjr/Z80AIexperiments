#!/usr/bin/env python3
"""Generate the pilot: jetdata.z80s for chequer6, jetdata7.z80s for 7.

    python3 tests/mkjetdata.py

The two files are the same sprite divided in a different place. Above
the division nothing else paints, so the background is one constant and
those rows are a COMPILED RUN OF PUSHES with the sky baked into the
transparent bytes and the single pixel ones: 5.5 T-states a byte, no
mask, and no clearing of the pose that was there. Below it the
background moves every frame, so those rows are a run-length stream
played over whatever is there, one entry a row:

    rep                 how many screen rows these ops draw. Two thirds
                        of the pilot's rows are the same as the one
                        above, so 96 rows come out as 47 entries
    ops                 0x01..0x10  skip n bytes
                        0x20+n      copy the n bytes that follow
                        0x40+n      fill n bytes with the byte that follows
                        0x00        end of row
    0x00                in place of a rep, the end of the stream
    0xFF lo hi          in place of a rep, the stream continues there

That last one is why this is a stream and not a bitmap: the free memory
under the screen is in pieces, and the pilot goes in whatever is left of
them once the board's run bank has had its share.

chequer6 divides at row 97, where its board starts. chequer7 divides at
81, where its city does - a city on the horizon paints over the pilot,
so sixteen more of his rows have to be masked against it every frame.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import city
import jetpack as J

X = 112                         # where the pilot stands, in pixels
Y = 48                          # and its top row
SPLIT = 97                      # the first row the board redraws, which
                                # is where the pilot divides
SPLIT7 = city.TOP               # and chequer7's, which is the city's top
                                # row: the city moves under the pilot, so
                                # everything from there down is redrawn
SKY = 0x11                      # CHQ4_C1, both nibbles: what is above the
                                # board, everywhere, this viewport having
                                # no haze. The generated file asserts it


def encode(by, kind):
    """One row's ops, over the 16 bytes the pilot is wide.

    A byte with one pixel covered is a mask op of its own - there are
    about two a row, and they are what keeps the outline one pixel wide
    where the silhouette does not land on a byte.
    """
    out, i, n = [], 0, len(kind)
    while i < n:
        if not kind[i]:
            k = 0
            while i + k < n and not kind[i + k]:
                k += 1
            i += k
            if i < n:                   # a skip at the end of a row is
                out.append([k])         # the end of the row
            continue
        if kind[i] > 1:                 # one pixel of it: 0x60 keeps the
            out.append([0x5E + kind[i], by[i]])         # screen's right
            i += 1                                      # pixel, 0x61 its
            continue                                    # left
        j = i
        while j < n and kind[j] == 1:
            j += 1
        while i < j:                    # fills where they pay, copies else
            k = 1
            while i + k < j and by[i + k] == by[i]:
                k += 1
            if k >= 3:
                out.append([0x40 + k, by[i]])
                i += k
                continue
            m = i
            while m < j:
                kk = 1
                while m + kk < j and by[m + kk] == by[m]:
                    kk += 1
                if kk >= 3:
                    break
                m += kk
            out.append([0x20 + m - i] + by[i:m])
            i = m
    return [b for op in out for b in op] + [0]


def run(rows, y0, y1, k):
    """The rows nothing else paints over, as a straight run of PUSHes.

    Up there the background is one constant, so a byte with a single
    pixel of pilot in it can have the sky baked into its other nibble
    rather than masked at runtime - and the transparent bytes can be
    baked too, which is what lets the whole box go down as PUSHes and
    is why the pose it replaces needs no clearing first.

    The pilot is 16 bytes wide, so a row is eight PUSHes and a DE
    reload wherever the pair changes; two thirds of the rows repeat the
    one above and reload nothing at all.
    """
    out = ["\njet_sky%d:       ; the rows nothing else paints over" % k,
           "        DI                      ; SP is about to be the screen",
           "        LD   (jet_sp),SP"]
    de, n = None, 0
    for y in range(y0, y1):
        by, kind = rows[y - Y]
        px = [SKY if not kind[i] else
              by[i] if kind[i] == 1 else
              by[i] | (SKY & 0x0F) if kind[i] == 2 else
              by[i] | (SKY & 0xF0) for i in range(len(kind))]
        out.append("        LD   SP,CHQ4_SCREEN + %d * 128 + %d"
                   % (y, X // 2 + len(px)))
        for i in range(len(px) - 2, -1, -2):
            v = px[i] | (px[i + 1] << 8)
            if v != de:
                out.append("        LD   DE,0x%04X" % v)
                de = v
            out.append("        PUSH DE")
            n += 1
    out += ["        LD   SP,(jet_sp)", "        EI", "        RET"]
    return out, n


def stream(rows, y0, y1):
    """The rows from y0 up to y1, with the repeats collapsed."""
    out, y = [], y0
    while y < y1:
        n = 1
        while y + n < y1 and rows[y + n - Y] == rows[y - Y]:
            n += 1
        by, kind = rows[y - Y]
        out += [n] + encode(by, kind)
        y += n
    return out + [0]


def defb(v, per=16):
    return "\n".join("        DEFB " + ",".join(str(x & 0xFF)
                                                for x in v[i:i + per])
                     for i in range(0, len(v), per))


def emit(here, name, split, what):
    """One file of streams, divided at the first row that is redrawn."""
    parts = ["; Generated by tests/mkjetdata.py - do not edit by hand.",
             "; The pilot, divided at row %d: %s." % (split, what),
             "; Above that line it is a run of PUSHes with the sky baked",
             "; in; below it, a stream to be played over what is there.",
             "\n        ASSERT (CHQ4_C1 & 255) == 0x%02X" % SKY,
             "\nJET_X:          EQU %d          ; the pilot's left edge" % X,
             "JET_Y:          EQU %d          ; and its top row" % Y,
             "JET_SPLIT:      EQU %d          ; where the redrawing starts"
             % split,
             "JET_W:          EQU %d           ; bytes wide" % (J.W // 2),
             "JET_POSES:      EQU 3           ; banking left, level, right",
             "\njet_pose:       ; the two halves of each pose",
             "\n".join("        DEFW jet_sky%d,jet_floor%d" % (k, k)
                       for k in range(3))]
    parts += ["\njet_sp:         DEFS 2          ; the run's way back"]
    tot = 0
    for k, way in enumerate((-1, 0, 1)):
        rows = J.rows(J.lean(J.pilot(), way))
        sky, _ = run(rows, Y, split, k)
        floor = stream(rows, split, Y + J.H)
        tot += len(floor)
        parts += sky
        parts += ["\njet_floor%d:     ; and the rows that are redrawn a"
                  " frame, which are over a background that moves and so"
                  % k,
                  "                ; have to be masked, and played back"
                  " rather than run",
                  defb(floor)]
    open(os.path.join(here, name), "w").write("\n".join(parts) + "\n")
    return tot


def main(here):
    a = emit(here, "jetdata.z80s", SPLIT, "chequer6, where the board starts")
    b = emit(here, "jetdata7.z80s", SPLIT7,
             "chequer7, where the city starts")
    rows = J.rows(J.pilot())
    drawn = sum(1 for by, kind in rows for k in kind if k)
    masked = sum(1 for by, kind in rows for k in kind if k > 1)
    print("pilot: %d bytes drawn of %d, %d of them one pixel; three poses, "
          "%d bytes of stream below row %d and %d below %d, the rows above "
          "being runs" % (drawn, J.W // 2 * J.H, masked, a, SPLIT, b, SPLIT7))


if __name__ == "__main__":
    main(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
