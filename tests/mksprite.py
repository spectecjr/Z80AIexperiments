#!/usr/bin/env python3
"""Compiling a masked sprite so that it can be drawn anywhere.

The pilot and the tree are the same problem: a shape with holes in it,
to be put down at a position only the caller knows, over a background
that has to show through the holes. A compiled sprite with absolute
addresses cannot move, so the way to make one relative on a Z80 is SP,
because it is the only pointer with an add - and the way to keep that
cheap is to arrange the whole sprite as ONE DESCENDING WALK of it: rows
bottom upwards, bytes right to left, so every step is a subtraction and
the caller's only job is to put SP at the byte after the bottom right
corner.

    a run of solid bytes    PUSH DE a pair, 5.5 T-states a byte, with
                            DE reloaded only where the pair changes
    a single byte           POP BC / LD C,n / PUSH BC, which reads the
                            byte beside it and writes it back unchanged
    one pixel of sprite     POP BC / AND / OR / PUSH BC, the only
                            read-modify-write left
    getting there           LD HL,-d / ADD HL,SP / LD SP,HL, or DEC SP
                            where the step is small enough

Nothing in here knows what it is drawing: the caller hands it the rows
in the four kinds jetpack.py and tree.py both emit.
"""


class Walk:
    """One sprite's worth of emitted code, and what it will cost."""

    def __init__(self, label, w, h, ret):
        self.out = ["\n%s:         ; SP is the byte after the bottom"
                    " right corner" % label]
        self.w, self.ret = w, ret
        self.t = 0
        self.de = None
        self.at = (h - 1) * 128 + w     # where SP is, as an offset into
                                # the box: the caller puts it at the byte
                                # after the bottom right corner, and the
                                # rows are 128 apart

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
        i = self.w - 1
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
        self.op("JP   %s" % self.ret, 10)
        return self.out, self.t


def walk(label, rows, w, h, ret):
    """A whole sprite: its rows, bottom upwards. Returns (lines, T-states)."""
    p = Walk(label, w, h, ret)
    for y in range(h - 1, -1, -1):
        p.row(y, *rows[y])
    return p.done()


