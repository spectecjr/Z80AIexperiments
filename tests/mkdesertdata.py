#!/usr/bin/env python3
"""Generate the desert: two chunks of compiled rear layer, and the
front layer's spans.

    python3 tests/mkdesertdata.py

THE REAR LAYER IS COMPILED, one run of PUSHes a (row, phase). A run
holds two whole periods of the row - 128 PUSHes - so that entering it
at the right place gives any rotation of the pattern, and the pushes
left over at the end spill into the row above, which is drawn next
because the band is drawn bottom upwards. That is road2's trick with
the road's window, over a picture instead of a road.

FOUR PHASES, not two. The layer moves by pixels, and a pixel is half a
byte; a run can be entered at a pair, which is four pixels; and `SP`
could take up the odd byte but then the row's last byte falls outside
the pairs and wants a store of its own. Compiling the pattern at all
four pixel offsets instead costs twice the memory and removes that
whole limb: the entry is (64 - offset/4) and the stack pointer is
always the row's right hand end.

Each run carries a table of its 64 entry points, four bytes each: the
`DE` the run wants at that point, because a run reloads `DE` only where
the colour changes, and where in the run to go. Six-byte stubs would be
twenty T-states a row cheaper and half as much again in memory, and the
memory is what is short here.

THE FRONT LAYER IS SPANS, because it has to leave the rear layer
showing between its dunes. Per row, the runs of dune body and of lit
crest, in layer pixels; the Z80 subtracts the offset, splits whatever
crosses the screen's edge, and draws each one with a read-modify-write
at either end where the edge lands inside a byte.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desert as D                                      # noqa: E402

BANK0 = 0x20                    # LMPR: RAM over ROM 0, and the page the
FIRST = int(os.environ.get("DESERT_FIRST", 16))     # map has spare - which
SET = os.environ.get("DESERT_SET", "")              # is a different page
                                # in a demo whose board takes more chunks,
                                # so both it and the file names are given
WINDOW = 0x7F00                 # what LMPR maps, less the caller's stack


def pattern(px, phase):
    """One row of the rear layer at one pixel phase, as MODE 4 bytes."""
    return [(px[(2 * k + phase) % D.PERIOD] << 4)
            | px[(2 * k + phase + 1) % D.PERIOD] for k in range(D.STRIDE)]


def run(by):
    """The pushes for one (row, phase), and where each entry point is.

    Push k writes the pattern pair (63 - k) mod 64, so the run is the
    row twice over, descending - which is the order PUSH writes in.

    An entry is three words: the DE the run needs at that point, where
    to go, and WHERE TO STOP. A row wants exactly 64 pushes and a run
    entered at s has 128 - s left in it, so without the third the other
    64 - s spill into the row above and are thrown away - 22,528
    T-states in the worst frame. The caller writes a JP over the stop
    and puts the three bytes back afterwards, which is 144 T-states a
    row against an average of 352 of spill.
    """
    pairs = [by[2 * i] | (by[2 * i + 1] << 8) for i in range(64)]
    ops, offs, de = [], [], None
    for k in range(128):
        v = pairs[(63 - k) % 64]
        offs.append(sum(len(o) for o in ops))
        if v != de:
            ops.append([0x11, v & 255, v >> 8])         # LD DE,nn
            de = v
        ops.append([0xD5])                              # PUSH DE
    offs.append(sum(len(o) for o in ops))
    code = [b for o in ops for b in o]
    ent = [(pairs[(63 - s) % 64], offs[s], offs[s + 64]) for s in range(64)]
    return code, ent


def defb(v, per=16):
    return "\n".join("        DEFB " + ",".join(str(x & 0xFF)
                                                for x in v[i:i + per])
                     for i in range(0, len(v), per))


def chunks(rows):
    """Share the rows out, bottom upwards, so a frame walks the bank."""
    out, cur, used = [], [], 0
    for r in rows:
        want = sum(len(run(pattern(r[1], p))[0]) + 6 * 64 + 3
                   for p in range(4))
        if used + want > WINDOW - 1024:
            out.append(cur)
            cur, used = [], 0
        cur.append(r)
        used += want
    out.append(cur)
    return out


def emit_chunks(here, back):
    """The rear layer's runs, cut by row into chunks of their own.

    Each chunk carries its own tables of rows - one a phase, because
    which run a row wants depends on the phase and nothing else - at the
    foot of it, with a zero for the end of them and the chunk that comes
    after. That is chequer5's band table, and it means the row loop
    needs nothing from outside the chunk it is in.
    """
    rows = [(y, back[y]) for y in range(D.ROWS - 1, -1, -1)]     # bottom up
    cut, n = chunks(rows), 0
    for k, part in enumerate(cut):
        nxt = BANK0 + FIRST + 2 * (k + 1) if k + 1 < len(cut) else 0
        parts = ["; Generated by tests/mkdesertdata.py - do not edit.",
                 "; Chunk %d of the desert's rear layer: the rows %d to %d,"
                 % (k, part[0][0], part[-1][0]),
                 "; each compiled at four pixel phases, with the table of",
                 "; entry points that a rotation of it is reached through.",
                 "; C9_RET comes from the resident assembly: a run's way",
                 "; back is the one address the bank has to know.",
                 "\n        ORG 0x0000",
                 "        DEFW des_t0,des_t1,des_t2,des_t3"]
        for p in range(4):
            parts.append("\ndes_t%d:         ; this chunk's rows at phase %d,"
                         " bottom upwards" % (p, p))
            parts += ["        DEFW des_e%d_%d" % (y, p) for y, _ in part]
            parts.append("        DEFW 0\n        DEFB 0x%02X       ; and the"
                         " chunk that comes after" % nxt)
        for y, px in part:
            for p in range(4):
                code, ent = run(pattern(px, p))
                parts.append("\ndes_e%d_%d:      ; row %d, phase %d: the DE"
                             " it needs, where to go and where to stop"
                             % (y, p, y, p))
                parts.append("\n".join(
                    "        DEFW %d,des_r%d_%d + %d,des_r%d_%d + %d"
                    % (v, y, p, at, y, p, stop) for v, at, stop in ent))
                parts.append("\ndes_r%d_%d:" % (y, p))
                parts.append(defb(code))
                parts.append("        JP C9_RET")
                n += len(code) + 384 + 3
        parts.append("\n        ASSERT $ <= 0x%04X       ; the window, less"
                     " the caller's stack" % WINDOW)
        open(os.path.join(here, "desert%srun%d.z80s" % (SET, k)), "w").write(
            "\n".join(parts) + "\n")
    return cut, n


def emit_resident(here):
    """The EQUs, and the front layer's spans."""
    parts = ["; Generated by tests/mkdesertdata.py - do not edit by hand.",
             "; What the resident code needs: where the band is, and the",
             "; front layer's spans. The rear layer's rows are tabled in",
             "; the chunks themselves, the way the board's bands are.",
             "\nC9_TOP:         EQU %d          ; the band's first scanline"
             % D.TOP,
             "C9_ROWS:        EQU %d          ; and how many of them"
             % D.ROWS,
             "C9_SKY:         EQU 0x%04X      ; the board's own sky, a pair"
             % (0x1111 * D.SKY),
             "C9_BANK0:       EQU 0x%02X        ; the rear layer's first chunk"
             % (BANK0 + FIRST),
             "\nc9_spans:       ; the front layer, a row at a time:",
             "                ; first pixel, last pixel, colour, and",
             "                ; 255 in place of a first pixel ends a row"]
    nsp = 0
    for y in range(D.ROWS):
        parts.append("        DEFB " + ",".join(
            "%d,%d,0x%02X" % (x0, x1, 0x11 * c) for x0, x1, c in D.SPANS[y])
            + (",255" if D.SPANS[y] else "255"))
        nsp += len(D.SPANS[y])
    open(os.path.join(here, "desert%sdata.z80s" % SET), "w").write(
        "\n".join(parts) + "\n")
    return nsp


def main(here):
    back = D.rear()
    cut, n = emit_chunks(here, back)
    nsp = emit_resident(here)
    print("desert%s: %d rows of rear layer at four phases in %d chunks "
          "from page %d, %d bytes; %d front spans"
          % (SET, D.ROWS, len(cut), FIRST, n, nsp))


if __name__ == "__main__":
    main(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
