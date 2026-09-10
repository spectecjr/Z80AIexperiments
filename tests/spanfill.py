#!/usr/bin/env python3
"""A model of spanfill.z80s, and the workload it is measured against.

The workload is a floor's worth of spans: a scanline crossed by a fixed
number of cell boundaries that converge with distance, in colours that
change from cell to cell. It is not a real landscape - it is the shape
of the work a real one hands to a span filler, which is what is being
measured.
"""
W, H, STRIDE = 256, 192, 128
TOP, ROWS = 64, 128             # the region the floor covers
CHAIN = 64                      # PUSHes in the run


def spans(cols, row):
    """Where the boundaries fall on one scanline, in whole PUSHes.

    The columns converge towards the middle as the row goes up, which
    is what perspective does to a grid, and every span is a whole
    number of PUSHes because a PUSH is two pixels.
    """
    t = (row + 8) / (ROWS + 8)          # 1 at the bottom, small at the top
    out, wide = [], STRIDE // 2
    for i in range(1, cols):
        x = wide / 2 + (i - cols / 2) * (wide / cols) * t
        out.append(max(0, min(wide, int(round(x)))))
    return [0] + out + [wide]


def frame(cols):
    """The screen the Z80 should draw, and the list it draws it from."""
    buf = bytearray(STRIDE * H)
    lst = []
    for r in range(ROWS):
        b = spans(cols, r)
        y = TOP + r
        for i in range(len(b) - 1, 0, -1):
            n = b[i] - b[i - 1]
            if not n:
                continue
            c = (7 + ((i * 5 + r // 8) & 7)) & 15
            lst += [CHAIN - n, c * 0x11]
            for x in range(b[i - 1] * 2, b[i] * 2):
                buf[y * STRIDE + x] = c * 0x11
        lst.append(0)
    return buf, lst


def cost(rows, spans_a_row, bytes_a_row=STRIDE):
    """What spanfill.z80s costs, from its measured parts.

    92 T-states a scanline, 63 a span and 5.5 a byte - all three
    measured by tests/test_spanfill.py, not estimated.
    """
    return int(rows * (92 + spans_a_row * 63 + bytes_a_row * 5.5))
