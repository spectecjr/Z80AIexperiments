#!/usr/bin/env python3
"""Compile the pilot so that he can be drawn anywhere: jetmove.z80s.

    python3 tests/mkjetmove.py

chequer8's compiled pilot is 96 rows in 14,400 T-states and every
address in it is absolute, which is only possible because he stands
still. chequer9's moves, so the same trick has to be made relative -
and the way to do that on a Z80 is to do everything through the stack
pointer, because SP is the only pointer with an add:

    a run of solid bytes    PUSH DE a pair, 5.5 T-states a byte, with
                            DE reloaded only where the pair changes
    a single byte           POP BC / LD C,n / PUSH BC, which reads the
                            byte beside it and writes it back unchanged
    one pixel of pilot      POP BC / AND / OR / PUSH BC, the only
                            read-modify-write left
    getting there           LD HL,-d / ADD HL,SP / LD SP,HL, or DEC SP
                            where the step is small enough

The whole sprite is one walk of SP from the bottom right corner of his
box to the top left: rows from the bottom up, bytes right to left, so
every step is a subtraction and the caller's only job is to put SP at
the corner. What it costs against the absolute version is the steps -
16,116 T-states against 14,401, measured in the frame - and what it
buys is that he can go anywhere.

HE MOVES IN WHOLE BYTES sideways, which is two pixels. A pixel of
horizontal travel would want the sprite compiled at both phases and
a mask on every byte of him rather than 110 of them; two pixel steps
at 25 Hz are not visible as steps on a sprite this size.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jetpack as J                                     # noqa: E402

W = J.W // 2                    # bytes wide
BANK = 0x38                     # LMPR: RAM over ROM 0, and the page the
                                # map has spare past the desert's
WINDOW = 0x7F00                 # what LMPR maps, less the caller's stack


class Pose:
    """One pose's worth of emitted code, and what it will cost."""

    def __init__(self, k):
        self.out = ["\njet_m%d:         ; SP is the byte after his bottom"
                    " right corner" % k]
        self.t = 0
        self.de = None
        self.at = (J.H - 1) * 128 + W   # where SP is, as an offset
                                # into his box: the caller puts it at
                                # the byte after his bottom right
                                # corner, and his rows are 128 apart

    def op(self, text, t):
        self.out.append("        " + text)
        self.t += t

    def to(self, at):
        """Walk SP back to an offset, which is always a step backwards."""
        d = self.at - at
        if not d:
            return
        if d <= 2:                      # two DEC SP are cheaper than the
            for _ in range(d):          # arithmetic, and one is much
                self.op("DEC  SP", 6)
        else:
            self.op("LD   HL,-%d" % d, 10)
            self.op("ADD  HL,SP", 11)
            self.op("LD   SP,HL", 6)
        self.at = at

    def pair(self, at, keep, put):
        """One byte, read back with the one beside it and written again.

        POP takes the byte SP points at into C and the one above it into
        B, so C is always the byte in question and B goes back untouched
        - and PUSH puts both back where they came from, leaving SP where
        it started.
        """
        self.to(at)
        self.op("POP  BC", 10)
        if keep is None:
            self.op("LD   C,0x%02X" % put, 7)
        else:
            self.op("LD   A,C", 4)
            self.op("AND  0x%02X" % keep, 7)
            if put:
                self.op("OR   0x%02X" % put, 7)
            self.op("LD   C,A", 4)
        self.op("PUSH BC", 11)
        self.at = at

    def row(self, y, by, kind):
        """One scanline, right to left, so that SP only ever descends."""
        base = y * 128
        i = W - 1
        while i >= 0:
            if not kind[i]:                     # transparent: whatever is
                i -= 1                          # behind him stays
                continue
            if kind[i] > 1:                     # one pixel of it is his
                m = 0x0F if kind[i] == 2 else 0xF0
                self.pair(base + i, m, by[i])
                i -= 1
                continue
            j = i                               # a run of whole bytes
            while j >= 0 and kind[j] == 1:
                j -= 1
            lo, n = j + 1, i - j
            for p in range(i - 1, lo + (n & 1) - 1, -2):
                self.to(base + p + 2)
                v = by[p] | (by[p + 1] << 8)
                if v != self.de:
                    self.op("LD   DE,0x%04X" % v, 10)
                    self.de = v
                self.op("PUSH DE", 11)
                self.at = base + p
            if n & 1:                           # PUSH writes two bytes
                self.pair(base + lo, None, by[lo])
            i = lo - 1

    def done(self):
        self.op("JP   CQ9_RET", 10)
        return self.out, self.t


def main(here):
    parts = ["; Generated by tests/mkjetmove.py - do not edit by hand.",
             "; The pilot as code that can be drawn anywhere: one walk of",
             "; the stack pointer from the bottom right corner of his box",
             "; to the top left. The caller puts SP there and jumps in;",
             "; CQ9_RET, from the resident assembly, is the way back.",
             "\n        ORG 0x0000",
             "jet_move:       ; banking left, level, right",
             "        DEFW jet_m0,jet_m1,jet_m2",
             "\nJET_W:          EQU %d           ; bytes wide" % W,
             "JET_H:          EQU %d           ; and scanlines tall" % J.H]
    ts = []
    for k, way in enumerate((-1, 0, 1)):
        rows = J.rows(J.lean(J.pilot(), way))
        p = Pose(k)
        for y in range(J.H - 1, -1, -1):        # bottom row first
            p.row(y, *rows[y])
        out, t = p.done()
        parts += out
        ts.append(t)
    parts.append("\n        ASSERT $ <= 0x%04X       ; the window, less the"
                 " caller's stack" % WINDOW)
    open(os.path.join(here, "jetmove.z80s"), "w").write("\n".join(parts) + "\n")
    open(os.path.join(here, "jetmoveequ.z80s"), "w").write(
        "; Generated by tests/mkjetmove.py - do not edit by hand.\n"
        "; What the resident code needs to know about the pilot's page.\n"
        "\nJET_BANK:       EQU 0x%02X      ; LMPR: RAM over ROM 0\n"
        "JET_POSE:       EQU 0x0000      ; the table of poses, at its foot\n"
        "JET_W:          EQU %d\nJET_H:          EQU %d\n"
        % (BANK, W, J.H))
    print("jetmove.z80s: three poses, %d T-states each by the instruction "
          "count (%d, %d, %d)" % (sum(ts) // 3, *ts))


if __name__ == "__main__":
    main(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
