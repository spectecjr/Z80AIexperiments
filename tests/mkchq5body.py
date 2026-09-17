#!/usr/bin/env python3
"""Compile a row loop body per (band, phase), and cut the bank by band.

    python3 tests/mkchq5body.py

chequer4's band loop patches six bytes into the row loop to set a band
up - the row's last byte, the value set's address, whether the stack
pointer shifts, and the run to jump to - and at 454 T-states a band
that is a quarter of chequer5's frame. Precomputing those six bytes
does not help much, because six `LD (nn),A` are 78 of it and a table
still has to do them.

So instead the row loop itself is compiled, one copy per (band, phase),
with all six baked in. The band loop then patches *one* address - the
jump the row loop turns round on - and a row costs exactly what it did.
There are 2,080 of those pairs, because the phase of a band of width p
is in [0, p) and the widths run 1..64, and a body is 30 bytes: 62K,
which is why this wants a paged bank and would not have been thinkable
in a flat 64K.

THE BANK IS CUT BY BAND, which is what keeps the paging down to three
`OUT`s a frame. The board is drawn widest square first and a band uses
exactly one run, so bodies *and* runs are walked in the same order: a
chunk holds the bodies, the runs, the value sets and the band table for
a stretch of bands, and needs nothing from any other chunk. The band
table's terminator says which chunk comes next, and every chunk's band
table is at its foot, so switching is an OUT and a pointer.
"""
import os
import sys

os.environ.setdefault("HARRIER_MINP", "1")      # the full depth viewport
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chequer3 as C                            # noqa: E402
import mkchq3data as M3                         # noqa: E402
import mkchq4data as M4                         # noqa: E402

PRE = M3.PRE                                    # chq5
SET = os.environ.get("CHQ_SET", "5")            # whose chunks these are
WINDOW = 0x7F00                 # the 32K LMPR maps, less the caller's stack
BANK0 = 0x20                    # LMPR for the first chunk: RAM over ROM 0
PAGES = [0, 2, 4, 14, 16, 18,   # and the pages the chunks go in, stepping
         20, 22, 24, 26, 28, 30]    # over the swap masks at 6 and 8 and
                                    # the two screens at 10 and 12
BODY = 30                       # bytes a compiled body
ROWS0 = int(os.environ.get("CHQ_ROWS0", 77))    # the shortest board a
ROWS1 = int(os.environ.get("CHQ_ROWS1", 114))   # horizon may give, and
                                                # the tallest


def body(p, ph, which):
    """The row loop with one band and phase baked into it.

    The phase says which run (its bottom bit), whether the stack
    pointer shifts (the next bit, and inverted - a clear bit is a
    shift), and which of the run's entry points to jump to (the rest).
    """
    t = ph & 1
    ops, ent, _ = M3.build(p, t)
    at, edge = ent[C.kmax(p) - 1 - (ph >> 2)]
    val = "chq4_val + %d" % (32 * which[(p, t)])
    return "\n".join([
        "%s_y%d_%d:" % (PRE, p, ph),
        "        LD   A,(DE)             ; this row's mask",
        "        XOR  %d" % edge,        # the row's last byte, turned round
        "        LD   (HL),A",
        "        LD   A,(DE)",
        "        DEC  DE",
        "        AND  0x10               ; the mask again, as the offset to",
        "        ADD  A,(%s) & 255       ; the complement of this run's" % val,
        "        EXX                     ; values",
        "        LD   L,A",
        "        LD   H,(%s) >> 8" % val,
        "        LD   SP,HL",
        "        POP  BC",
        "        POP  DE",
        "        POP  HL",
        "        POP  IX",
        "        POP  IY",
        "        POP  AF",
        "        EXX",
        "        LD   SP,HL              ; the runs fill rightwards to left",
        "        %s" % ("NOP " if (ph >> 1) & 1 else "INC  SP"),
        "        EXX",
        "        JP   %s_r%d_%d + %d" % (PRE, p, t, at)])


def runbytes(p):
    """What both of a width's runs take."""
    return sum(sum(len(o) for o in M3.build(p, t)[0]) + 3 for t in (0, 1))


def chunks(band):
    """Share the bands out, widest first, so that a chunk is a stretch
    of the screen and a frame walks the bank forwards."""
    out, cur, used = [], [], 0
    for n, p in band:
        want = p * BODY + 2 * p + runbytes(p) + 3      # bodies, table, runs
        if used + want > WINDOW - 1024:               # band table and values
            out.append(cur)
            cur, used = [], 0
        cur.append((n, p))
        used += want
    out.append(cur)
    return out


def horizons(here, cut):
    """Where to enter the band table for each horizon that is allowed.

    The board's widths are a function of (row - horizon) and nothing
    else, so ONE band table serves every horizon: a lower horizon is a
    taller board and simply starts further down the table, at the band
    holding the bottom row of the screen. The bands below that one are
    the ones that would be off the bottom of the screen.

    A horizon is allowed when the screen's bottom row is the last row
    of its band, because a band is drawn whole. Which rows those are
    depends on where the bands fall: near the horizon a band is a
    scanline or two, so most rows are allowed, and the wide bands at
    the bottom of the screen rule out a run of rows each.
    """
    out, rows = [], sum(n for n, _ in M4.bands())
    for k, part in enumerate(cut):
        at = 0
        for n, p in part:
            if ROWS0 <= rows <= ROWS1:                  # the range asked for
                out.append((191 - rows, BANK0 + PAGES[k], at, rows, p))
            rows -= n
            at += 3
    parts = ["; Generated by tests/mkchq5body.py - do not edit by hand.",
             "; Every horizon the board can have, and how to draw it: the",
             "; chunk the bottom band is in, where in that chunk's band",
             "; table it is, how many scanlines of board there are, and",
             "; how wide the widest square is - which is what the phase",
             "; accumulator is seeded with. Five bytes a horizon, lowest",
             "; horizon (the tallest board) first.",
             "\nCHQ4_HZ0:       EQU %d          ; the first horizon here"
             % min(h for h, _, _, _, _ in out),
             "CHQ4_HZN:       EQU %d          ; and how many there are"
             % len(out),
             "\nchq4_hztab:"]
    for hz, bank, at, n, p in sorted(out):
        parts.append("        DEFB 0x%02X       ; horizon %d: %d scanlines,"
                     " widest square %d" % (bank, hz, n, p))
        parts.append("        DEFW chq4_band + %d" % at)
        parts.append("        DEFB %d" % n)
        parts.append("        DEFB %d" % (p + 1))
    open(os.path.join(here, "chequer%shz.z80s" % SET), "w").write(
        "\n".join(parts) + "\n")
    return out


def emit(here):
    vtab, which = M4.values()
    band = M4.bands()
    cut = chunks(band)
    for k, part in enumerate(cut):
        nxt = BANK0 + PAGES[k + 1] if k + 1 < len(cut) else 0
        parts = ["; Generated by tests/mkchq5body.py - do not edit by hand.",
                 "; Chunk %d of chequer5's bank: the bands %d to %d, their"
                 % (k, part[0][1], part[-1][1]),
                 "; compiled row loop bodies, their runs and the value sets.",
                 "\n        ORG 0x0000",
                 "chq4_band:      ; rows, and this band's table of bodies",
                 "\n".join("        DEFB %d\n        DEFW %s_t%d"
                           % (n, PRE, p) for n, p in part),
                 "        DEFB 0,%d       ; and the chunk that comes after"
                 % nxt,
                 "\n        ALIGN 32",
                 "chq4_val:       ; BC, DE, HL, IX, IY and AF in the order a",
                 "                ; body POPs them, and sixteen bytes on, the",
                 "                ; same set with the two colours exchanged"]
        for v in vtab:
            parts.append("        DEFB " + ",".join(str(x) for x in v))
            parts.append("        DEFS 4")
            parts.append("        DEFB "
                         + ",".join(str(x ^ M4.SWAP) for x in v))
            parts.append("        DEFS 4")
        for _, p in part:
            parts.append("\n%s_t%d:        ; a body a phase" % (PRE, p))
            parts.append("\n".join("        DEFW %s_y%d_%d" % (PRE, p, ph)
                                   for ph in range(p)))
        for _, p in part:
            for ph in range(p):
                parts.append("\n" + body(p, ph, which))
        for _, p in part:
            for t in (0, 1):
                ops = M3.build(p, t)[0]
                parts.append("\n%s_r%d_%d:" % (PRE, p, t))
                parts.append(M3.defb([b for o in ops for b in o]))
                parts.append("        JP %s_ret" % PRE)
        parts.append("\n        ASSERT $ <= 0x%04X       ; the window, less"
                     " the caller's stack" % WINDOW)
        open(os.path.join(here, "chequer%sc%d.z80s" % (SET, k)), "w").write(
            "\n".join(parts) + "\n")
    hz = horizons(here, cut)
    print("chequer%shz.z80s: %d horizons, %d to %d scanlines of board"
          % (SET, len(hz), min(n for _, _, _, n, _ in hz),
             max(n for _, _, _, n, _ in hz)))
    n = sum(p for _, p in band)
    print("chequer%sc*.z80s: %d bodies of %d bytes in %d chunks of %d bands"
          % (SET, n, BODY, len(cut), len(band) // len(cut)))
    return len(cut)


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    emit(here)
