#!/usr/bin/env python3
"""Compile the pilot into code, in a page of its own: jetrun.z80s.

    python3 tests/mkjetrun.py

chequer6 plays the pilot back from a run-length stream, which costs
about 63 T-states for every byte it puts on the screen: an op to
dispatch, a count to unpack, and `LDIR` or a `DJNZ` to do the work. The
sprite does not change from frame to frame, though - only the
background under it does - so all of that is a decision that could have
been taken when the data was made.

So take it. Every byte of every row of every pose becomes code:

    a run of solid bytes     LD SP,end and a PUSH a pair, 5.5 T-states
                             a byte, with DE reloaded only where the
                             pair changes and SP only where a run does
                             not carry on from the one before
    an odd byte              LD A,n / LD (nn),A, because PUSH writes two
    one pixel of pilot       LD A,(nn) / AND / OR / LD (nn),A: the only
                             read-modify-write left, 110 bytes of the
                             sprite, and what keeps the outline one
                             pixel wide against a background that moves

THE WHOLE PILOT, EVERY FRAME. chequer6 and chequer7 divide him in two
and redraw only the rows something paints over, which is what makes a
pose change awkward: the rows nobody repaints have to be cleared first.
This does not. All 96 rows go down every frame, so a pose can change
whenever it likes - 96 rows rather than 47, and still a third of what 47
rows of stream cost.

The one place the division survives is in the data. Above the band that
scrolls there is nothing but sky, so up there the sky is baked into the
transparent bytes and the single pixel ones and the whole box is
PUSHes - no mask, and nothing left of the pose that was there. Below it
the background moves every frame, so only the pilot's own bytes are
touched.

IT LIVES IN A PAGE OF ITS OWN because at four bytes a pixel byte three
poses come to 10K, which is more than the 8K behind the screen has left.
The page is LMPR'd in over the board's bank, the routine is called
through a table at 0x0000, and the bank goes back afterwards - the
caller's stack is in chunk 0, which is the one thing the map has to
respect. See chequer8.md.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import city                                             # noqa: E402
import jetpack as J                                     # noqa: E402
from mkjetdata import X, Y, SKY                         # noqa: E402

SPLIT = city.TOP                # the first row something else paints

BANK = 0x2E                     # LMPR: RAM over ROM 0, and the page the
                                # bench's map has spare behind the screens
WINDOW = 0x7F00                 # what LMPR maps, less the caller's stack


class Pose:
    """One pose's worth of emitted code, and what it will cost."""

    def __init__(self, k):
        self.out = ["\njet8_%d:" % k,
                    "        DI                      ; SP is the screen",
                    "        LD   (jet8_sp),SP"]
        self.t = 4 + 20
        self.de = self.sp = self.a = None

    def op(self, text, t):
        self.out.append("        " + text)
        self.t += t

    def row(self, y, by, kind):
        """One scanline, right to left, so that SP only ever descends.

        Above the band that scrolls, nothing else paints, so the
        background is one constant and the whole 16 byte box goes down:
        the sky is baked into the transparent bytes and into the single
        pixel ones, which makes those rows PUSHes and nothing else, and
        means a pose that changes needs no clearing. Below it every byte
        of background moves, so only the pilot's own bytes are touched
        and the single pixel ones are read, masked and written.
        """
        base = y * 128 + X // 2
        if y < SPLIT:
            by = [SKY if not kind[i] else by[i] if kind[i] == 1 else
                  by[i] | (SKY & 0x0F) if kind[i] == 2 else
                  by[i] | (SKY & 0xF0) for i in range(len(kind))]
            kind = [1] * len(kind)
        i = len(kind) - 1
        while i >= 0:
            if not kind[i]:                     # transparent: the board's
                i -= 1
                continue
            if kind[i] > 1:                     # one pixel of it is ours
                m = 0x0F if kind[i] == 2 else 0xF0
                at = "CHQ4_SCREEN + %d" % (base + i)
                self.op("LD   A,(%s)" % at, 13)
                self.op("AND  0x%02X" % m, 7)
                if by[i]:                       # black needs no OR
                    self.op("OR   0x%02X" % by[i], 7)
                self.op("LD   (%s),A" % at, 13)
                self.a = None
                i -= 1
                continue
            j = i                               # a run of whole bytes
            while j >= 0 and kind[j] == 1:
                j -= 1
            lo, n = j + 1, i - j
            if self.sp != base + i + 1:
                self.op("LD   SP,CHQ4_SCREEN + %d" % (base + i + 1), 10)
                self.sp = base + i + 1
            for p in range(i - 1, lo + (n & 1) - 1, -2):
                v = by[p] | (by[p + 1] << 8)
                if v != self.de:
                    self.op("LD   DE,0x%04X" % v, 10)
                    self.de = v
                self.op("PUSH DE", 11)
                self.sp -= 2
            if n & 1:                           # PUSH writes two bytes
                if self.a != by[lo]:
                    self.op("LD   A,0x%02X" % by[lo], 7)
                    self.a = by[lo]
                self.op("LD   (CHQ4_SCREEN + %d),A" % (base + lo), 13)
            i = lo - 1

    def done(self):
        self.op("LD   SP,(jet8_sp)", 20)
        self.op("EI", 4)
        self.op("RET", 10)
        return self.out, self.t


def main(here):
    parts = ["; Generated by tests/mkjetrun.py - do not edit by hand.",
             "; The pilot as code, in a page LMPR maps at 0x0000. The three",
             "; poses are reached through the table at the foot of it, and",
             "; CHQ4_SCREEN comes from the resident assembly: the back",
             "; buffer is at a fixed address under the paged map, which is",
             "; what lets every one of these be an absolute store.",
             "\n        ORG 0x0000",
             "jet8_pose:      ; banking left, level, right",
             "        DEFW jet8_0,jet8_1,jet8_2",
             "jet8_sp:        DEFS 2"]
    ts = []
    for k, way in enumerate((-1, 0, 1)):
        rows = J.rows(J.lean(J.pilot(), way))
        p = Pose(k)
        for y in range(Y, Y + J.H):
            p.row(y, *rows[y - Y])
        out, t = p.done()
        parts += out
        ts.append(t)
    parts.append("\n        ASSERT $ <= 0x%04X       ; the window, less the"
                 " caller's stack" % WINDOW)
    open(os.path.join(here, "jetrun.z80s"), "w").write("\n".join(parts) + "\n")
    open(os.path.join(here, "jetrunequ.z80s"), "w").write(
        "; Generated by tests/mkjetrun.py - do not edit by hand.\n"
        "; What the resident code needs to know about the pilot's page.\n"
        "\nJET8_BANK:      EQU 0x%02X      ; LMPR: RAM over ROM 0, and the\n"
        "                                ; page the map has spare\n"
        "JET8_POSE:      EQU 0x0000      ; the table of poses, at its foot\n"
        % BANK)
    print("jetrun.z80s: three poses, %d T-states each by the instruction "
          "count (%d, %d, %d)" % (sum(ts) // 3, *ts))


if __name__ == "__main__":
    main(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
