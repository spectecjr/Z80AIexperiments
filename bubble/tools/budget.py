#!/usr/bin/env python3
"""
budget.py - SAM Coupe frame budget, and a checker for the [nT / na]
annotations that the assembly sources carry.

Two jobs:

 1. Derive the frame's memory-access budget from the SAM's timing, and
    turn the measured per-object costs into an object count. This is the
    arithmetic behind docs/BUBBLE_BOBBLE_SAM.md, kept runnable so the
    document cannot quietly drift away from the code.

 2. Re-derive every "; [11T / 3a]" annotation in bubble/*.z80s from a Z80
    timing table and report any that disagree. Hand-written cycle counts
    rot; this is how you keep them honest.

Run: python3 bubble/tools/budget.py [--check]
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..")

# --------------------------------------------------------------------------
# SAM Coupe frame timing
#
# 384 T per line at 6 MHz, 312 lines, so 119,808 T per frame at ~50.08 Hz.
# The ASIC grants the CPU one memory access per 8 T while the raster is in
# the 256 T display window, and one per 4 T over the remaining 128 T of
# border plus the 120 fully blanked lines.
# --------------------------------------------------------------------------

T_PER_LINE = 384
LINES = 312
DISPLAY_LINES = 192
DISPLAY_T = 256
CPU_HZ = 6_000_000


def frame_budget():
    blank_lines = LINES - DISPLAY_LINES
    per_display_line = DISPLAY_T // 8 + (T_PER_LINE - DISPLAY_T) // 4
    per_blank_line = T_PER_LINE // 4
    return (DISPLAY_LINES * per_display_line + blank_lines * per_blank_line,
            per_display_line, per_blank_line)


# Measured by bubble/tools/bbgfx.py from the compiled sprite code it emits.
COSTS = {
    "erase, flat backdrop (PUSH fill)":        239,
    "erase, over a platform (tile bank)":      880,
    "draw, opaque stack blit":                 397,
    "draw, masked compiled sprite":            538,
    "draw, hollow bubble (masked)":            577,
}

OVERHEAD = {
    "frame interrupt, buffer flip, input":     400,
    "object logic (48 x ~55)":                2640,
    "plan sweep, dispatch, draw records":     1800,
    "audio driver (budgeted, not written)":    600,
}


def report_budget():
    total, per_disp, per_blank = frame_budget()
    print("SAM Coupe frame")
    print("  %d T per line x %d lines = %d T at %.2f Hz"
          % (T_PER_LINE, LINES, T_PER_LINE * LINES,
             CPU_HZ / (T_PER_LINE * LINES)))
    print("  display line: %d slots   blank line: %d slots"
          % (per_disp, per_blank))
    print("  FRAME BUDGET: %d memory accesses" % total)
    print()
    print("  a MODE 4 screen is %d bytes; PUSH moves 2 bytes per 3 accesses," % 24576)
    print("  so the most that can be written in one frame is %d bytes (%.0f%%)."
          % (total * 2 // 3, 100.0 * (total * 2 // 3) / 24576))
    print("  Full-screen redraw is therefore impossible: dirty rectangles")
    print("  are not an optimisation here, they are the only option.")
    print()

    print("Per-object costs (measured):")
    for k, v in COSTS.items():
        print("  %-38s %5d a  (%6d T in display)" % (k, v, v * 8))
    print()

    spent = sum(OVERHEAD.values())
    print("Per-frame overheads:")
    for k, v in OVERHEAD.items():
        print("  %-38s %5d a" % (k, v))
    print("  %-38s %5d a" % ("subtotal", spent))
    avail = total - spent - int(0.05 * total)
    print("  %-38s %5d a  (after 5%% slack)" % ("available for blitting", avail))
    print()

    mixes = [
        ("all solid, flat backdrop",
         COSTS["erase, flat backdrop (PUSH fill)"] + COSTS["draw, opaque stack blit"]),
        ("all hollow bubbles, flat backdrop",
         COSTS["erase, flat backdrop (PUSH fill)"] + COSTS["draw, hollow bubble (masked)"]),
        ("Bubble Bobble mix (70% flat, 60% hollow)",
         int(0.70 * COSTS["erase, flat backdrop (PUSH fill)"]
             + 0.30 * COSTS["erase, over a platform (tile bank)"]
             + 0.60 * COSTS["draw, hollow bubble (masked)"]
             + 0.40 * COSTS["draw, opaque stack blit"])),
        ("worst case, all hollow over platforms",
         COSTS["erase, over a platform (tile bank)"] + COSTS["draw, hollow bubble (masked)"]),
    ]
    print("Objects fully redrawn per 50 Hz frame:")
    for name, per in mixes:
        print("  %-42s %4d a/obj -> %2d objects" % (name, per, avail // per))
    print()
    print("  The object table holds 48. Above the sustained figure the")
    print("  budget governor defers the lowest-priority objects, which are")
    print("  also not erased, so they hold their pixels for one more field")
    print("  and degrade to 25 Hz rather than flickering.")


# --------------------------------------------------------------------------
# Annotation checker
# --------------------------------------------------------------------------
#
# Each entry: T-states, memory accesses. Accesses = opcode bytes fetched
# + immediate bytes + data reads + data writes (PUSH/POP count 2).

def build_table():
    t = {}

    def add(pat, ts, acc):
        t[pat] = (ts, acc)

    R8 = ["A", "B", "C", "D", "E", "H", "L"]
    RR = ["BC", "DE", "HL", "SP"]

    for a in R8:
        for b in R8:
            add("LD %s,%s" % (a, b), 4, 1)
        add("LD %s,n" % a, 7, 2)
        add("LD %s,(HL)" % a, 7, 2)
        add("LD (HL),%s" % a, 7, 2)
        add("INC %s" % a, 4, 1)
        add("DEC %s" % a, 4, 1)
        add("ADD A,%s" % a, 4, 1)
        add("ADC A,%s" % a, 4, 1)
        add("SUB %s" % a, 4, 1)
        add("SBC A,%s" % a, 4, 1)
        add("AND %s" % a, 4, 1)
        add("OR %s" % a, 4, 1)
        add("XOR %s" % a, 4, 1)
        add("CP %s" % a, 4, 1)
        add("SLA %s" % a, 8, 2)
        add("SRL %s" % a, 8, 2)
        add("RL %s" % a, 8, 2)
        add("RR %s" % a, 8, 2)
        for n in range(8):
            add("BIT %d,%s" % (n, a), 8, 2)
            add("SET %d,%s" % (n, a), 8, 2)
            add("RES %d,%s" % (n, a), 8, 2)
    add("LD (HL),n", 10, 3)
    add("ADD A,n", 7, 2)
    add("ADC A,n", 7, 2)
    add("SUB n", 7, 2)
    add("AND n", 7, 2)
    add("OR n", 7, 2)
    add("XOR n", 7, 2)
    add("CP n", 7, 2)
    for r in RR:
        add("LD %s,nn" % r, 10, 3)
        add("INC %s" % r, 6, 1)
        add("DEC %s" % r, 6, 1)
        add("ADD HL,%s" % r, 11, 1)
        add("SBC HL,%s" % r, 15, 2)
        add("ADC HL,%s" % r, 15, 2)
    for r in ["BC", "DE", "HL", "AF"]:
        add("PUSH %s" % r, 11, 3)
        add("POP %s" % r, 10, 3)
    for r in ["IX", "IY"]:
        add("PUSH %s" % r, 15, 4)
        add("POP %s" % r, 14, 4)
        add("LD %s,nn" % r, 14, 4)
        add("INC %s" % r, 10, 2)
        add("LD SP,%s" % r, 10, 2)
        for s in ["BC", "DE", "SP", r]:
            add("ADD %s,%s" % (r, s), 15, 2)
        for a in R8:
            add("LD %s,(%s+d)" % (a, r), 19, 4)
            add("LD (%s+d),%s" % (r, a), 19, 5)
        add("LD (%s+d),n" % r, 19, 5)
        add("INC (%s+d)" % r, 23, 6)
        add("DEC (%s+d)" % r, 23, 6)
        add("CP (%s+d)" % r, 19, 4)
        for n in range(8):
            add("BIT %d,(%s+d)" % (n, r), 20, 5)
            add("SET %d,(%s+d)" % (n, r), 23, 6)
            add("RES %d,(%s+d)" % (n, r), 23, 6)
    add("LD SP,HL", 6, 1)
    add("LD (nn),SP", 20, 6)
    add("LD SP,(nn)", 20, 6)
    add("LD (nn),HL", 16, 5)
    add("LD HL,(nn)", 16, 5)
    for r in ["BC", "DE", "SP"]:
        add("LD (nn),%s" % r, 20, 6)
        add("LD %s,(nn)" % r, 20, 6)
    add("LD (nn),A", 13, 4)
    add("LD A,(nn)", 13, 4)
    add("LD A,(DE)", 7, 2)
    add("LD A,(BC)", 7, 2)
    add("LD (DE),A", 7, 2)
    add("LD (BC),A", 7, 2)
    add("INC (HL)", 11, 3)
    add("DEC (HL)", 11, 3)
    add("AND (HL)", 7, 2)
    add("OR (HL)", 7, 2)
    add("XOR (HL)", 7, 2)
    add("ADD A,(HL)", 7, 2)
    add("ADC A,(HL)", 7, 2)
    add("SUB (HL)", 7, 2)
    add("SBC A,(HL)", 7, 2)
    add("CP (HL)", 7, 2)
    add("EX DE,HL", 4, 1)
    add("EX AF,AF'", 4, 1)
    add("EXX", 4, 1)
    add("LDI", 16, 4)
    add("LDD", 16, 4)
    add("NEG", 8, 2)
    add("CPL", 4, 1)
    add("SCF", 4, 1)
    add("CCF", 4, 1)
    add("NOP", 4, 1)
    add("DI", 4, 1)
    add("EI", 4, 1)
    add("HALT", 4, 1)
    add("IM n", 8, 2)
    add("RLA", 4, 1)
    add("RRA", 4, 1)
    add("RLCA", 4, 1)
    add("RRCA", 4, 1)
    add("JP nn", 10, 3)
    add("JP (HL)", 4, 1)
    add("CALL nn", 17, 5)
    add("RET", 10, 3)
    add("RETI", 14, 4)
    add("JR d", 12, 2)
    add("DJNZ d", 13, 2)
    # OUT (n),A is D3 nn: the opcode and port bytes are memory accesses,
    # the I/O cycle itself is not.
    add("OUT (n),A", 11, 2)
    add("IN A,(n)", 11, 2)
    add("OUT (C),r", 12, 2)
    add("IN r,(C)", 12, 2)
    for cc in ["Z", "NZ", "C", "NC", "P", "M", "PE", "PO"]:
        add("JP %s,nn" % cc, 10, 3)
        add("CALL %s,nn" % cc, 17, 5)
        add("RET %s" % cc, 11, 3)
    for cc in ["Z", "NZ", "C", "NC"]:
        add("JR %s,d" % cc, 12, 2)
    return t


TABLE = build_table()
LINE = re.compile(r"^\s+([A-Z][A-Z0-9']*)\s*(.*?)\s*;\s*\[\s*(~?)(\d+)T\s*/\s*(~?)(\d+)a\s*\]")
COND = ("Z", "NZ", "C", "NC", "P", "M", "PE", "PO")


def normalise(op, args):
    """Reduce a real operand list to the table's key form."""
    args = args.split(";")[0].strip()
    parts = [p.strip() for p in args.split(",")] if args else []

    def kind(p):
        if p in ("A", "B", "C", "D", "E", "H", "L", "BC", "DE", "HL", "SP",
                 "IX", "IY", "AF", "AF'", "(HL)", "(BC)", "(DE)"):
            return p
        if re.match(r"^\((IX|IY)\s*\+", p):
            return "(%s+d)" % p[1:3]
        if p.startswith("(") and p.endswith(")"):
            return "(nn)"
        return None

    if op in ("JR", "DJNZ"):
        if parts and parts[0] in COND:
            return "%s %s,d" % (op, parts[0])
        return "%s d" % op
    if op in ("JP", "CALL"):
        if parts and parts[0] in COND and len(parts) == 2:
            return "%s %s,nn" % (op, parts[0])
        if len(parts) == 1 and parts[0] == "(HL)":
            return "JP (HL)"
        return "%s nn" % op
    if op == "RET":
        return "RET %s" % parts[0] if parts and parts[0] in COND else "RET"
    if op == "IM":
        return "IM n"
    if op in ("OUT", "IN"):
        if parts and parts[-1] == "(C)":
            return "IN r,(C)"
        if parts and parts[0] == "(C)":
            return "OUT (C),r"
        return "OUT (n),A" if op == "OUT" else "IN A,(n)"
    if not parts:
        return op
    ks = []
    for p in parts:
        k = kind(p)
        if k is None:
            if op in ("BIT", "SET", "RES") and p.isdigit():
                k = p
            else:
                k = "nn" if (op in ("LD",) and len(parts) == 2
                             and kind(parts[0]) in ("BC", "DE", "HL", "SP", "IX", "IY")) else "n"
        ks.append(k)
    return "%s %s" % (op, ",".join(ks))


def check():
    bad = unknown = checked = 0
    for name in sorted(os.listdir(SRC)) + ["gen/bb_gfx.z80s"]:
        path = os.path.join(SRC, name)
        if not name.endswith(".z80s") or not os.path.isfile(path):
            continue
        for n, line in enumerate(open(path), 1):
            m = LINE.match(line.rstrip("\n"))
            if not m:
                continue
            op, args, ta, ts, aa, acc = m.groups()
            ts, acc = int(ts), int(acc)
            key = normalise(op, args)
            if key not in TABLE:
                unknown += 1
                continue
            checked += 1
            et, ea = TABLE[key]
            if (not ta and et != ts) or (not aa and ea != acc):
                bad += 1
                print("  %s:%d  %-22s annotated [%dT/%da] expected [%dT/%da]"
                      % (name, n, key, ts, acc, et, ea))
    print("annotations: %d checked, %d disagree, %d not in the table"
          % (checked, bad, unknown))
    return bad


if __name__ == "__main__":
    report_budget()
    if "--check" in sys.argv or True:
        print()
        print("Annotation check")
        sys.exit(1 if check() else 0)
