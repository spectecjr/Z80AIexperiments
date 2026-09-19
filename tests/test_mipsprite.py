#!/usr/bin/env python3
"""What a compiled 64x80 sprite costs, at every size down to 8x10.

    python3 tests/test_mipsprite.py

Compiles the chain built by `mipsprite.py` into Z80 machine code, runs
each level on the emulator against a 24K MODE 4 screen, checks every
byte against the model, and reports the T-states. There is no .z80s
file and no assembler: a compiled sprite *is* generated code, so the
generator is the source, exactly as `mkchq3data.py` is for chequer3's
run bank.

Two shapes are measured for each level:

  dispatch  one straight-line block a source row, reached through a
            row program - so the height is whatever the program asks
            for and only the width is quantised to the level

  whole     the level's rows compiled into one straight-line block at
            one height - no dispatch at all, and the register cache
            carries across rows, but a block per height

and the erase underneath them, as a PUSH fill of the same box.
"""
import sys
from collections import Counter

import z80

import mipsprite as M

SCREEN = 0x8000
SCRSIZE = 24576
RUNTIME = 0x0100
CODE = 0x0400
STACK = 0xFE00
HALTADDR = 0x0000
FRAME = 100000
BG = M.BACKDROP                 # the flat colour an erase puts back

SPX, SPY = 20, 40               # where the sprite is put, in bytes and rows


# ------------------------------------------------------------- an assembler

class Code:
    """Emit bytes, remember labels, and total the T-states as it goes."""

    def __init__(self, org):
        self.org = org
        self.b = bytearray()
        self.t = 0

    @property
    def pc(self):
        return self.org + len(self.b)

    def _e(self, t, *bs):
        self.b += bytes(bs)
        self.t += t
        return self

    def w(self, nn):
        return (nn & 0xFF, (nn >> 8) & 0xFF)

    def exx(self):          return self._e(4, 0xD9)
    def di(self):           return self._e(4, 0xF3)
    def ei(self):           return self._e(4, 0xFB)
    def nop(self):          return self._e(4, 0x00)
    def ret(self):          return self._e(10, 0xC9)
    def halt(self):         return self._e(4, 0x76)
    def dec_sp(self):       return self._e(6, 0x3B)
    def add_hl_sp(self):    return self._e(11, 0x39)
    def ld_sp_hl(self):     return self._e(6, 0xF9)
    def ld_sp_iy(self):     return self._e(10, 0xFD, 0xF9)
    def ld_a_de(self):      return self._e(7, 0x1A)
    def inc_e(self):        return self._e(4, 0x1C)
    def ld_l_a(self):       return self._e(4, 0x6F)
    def ld_h_a(self):       return self._e(4, 0x67)
    def jp_hl(self):        return self._e(4, 0xE9)
    def jp(self, nn):       return self._e(10, 0xC3, *self.w(nn))
    def ld_nn_sp(self, nn): return self._e(20, 0xED, 0x73, *self.w(nn))
    def ld_sp_nn(self, nn): return self._e(20, 0xED, 0x7B, *self.w(nn))
    def ld_iy_nn(self, nn): return self._e(20, 0xFD, 0x2A, *self.w(nn))
    def ld_ix(self, nn):    return self._e(14, 0xDD, 0x21, *self.w(nn))
    def push_ix(self):      return self._e(15, 0xDD, 0xE5)

    LOAD = {"BC": (10, 0x01), "DE": (10, 0x11), "HL": (10, 0x21)}
    PUSH = {"BC": (11, 0xC5), "DE": (11, 0xD5), "HL": (11, 0xE5)}

    def ld(self, r, nn):
        t, op = self.LOAD[r]
        return self._e(t, op, *self.w(nn))

    def push(self, r):
        t, op = self.PUSH[r]
        return self._e(t, op)

    def sp_add(self, d, window=False):
        """SP += d, through HL. Costs HL; the caller marks it dead.

        The interrupt window goes between the add and the store, so the
        new pointer is already in HL and nothing has to be saved.
        """
        self.ld("HL", d & 0xFFFF)
        self.add_hl_sp()
        if window:
            self.window()
        return self.ld_sp_hl()

    def window(self):
        """Let the interrupt in: 22 T-states, scroll8's measured figure."""
        self.ld_sp_iy()
        self.ei()
        self.nop()
        return self.di()


# --------------------------------------------------------- the compiler

def ops_for_row(lv, y):
    """A row as ('push', value) and ('skip', bytes), right to left.

    SP enters at the row's right edge and must leave at its left edge,
    so the skips account for every uncovered byte.
    """
    by, _ = lv.rows[y]
    out = []
    pos = lv.wb
    for s, e in reversed(lv.runs[y]):
        if pos > e:
            out.append(("skip", pos - e))
        for i in range(e - 2, s - 1, -2):
            out.append(("push", (by[i + 1] << 8) | by[i]))
        pos = s
    if pos:
        out.append(("skip", pos))
    return out


def next_use(ops, i, value):
    for j in range(i, len(ops)):
        if ops[j][0] == "push" and ops[j][1] == value:
            return j
    return len(ops)


def next_kill(ops, i):
    """Where HL next gets destroyed by an SP adjustment."""
    for j in range(i, len(ops)):
        if ops[j][0] in ("rowstep",) or (ops[j][0] == "skip" and ops[j][1] > 4):
            return j
    return len(ops)


def emit_ops(c, ops, ixval, regs, cache=True):
    """Emit a run of ops with a Belady cache over BC, DE and HL."""
    if not cache:
        ixval = None
    for i, op in enumerate(ops):
        kind, arg = op[0], op[1]
        if kind == "skip":
            if arg <= 4:                    # DEC SP is 6, the HL form 27
                for _ in range(arg):
                    c.dec_sp()
            else:
                c.sp_add(-arg)
                regs["HL"] = None
            continue
        if kind == "rowstep":
            c.sp_add(arg, ops[i][2])
            regs["HL"] = None
            continue
        v = arg
        if not cache:                       # what a sprite costs with no
            c.ld("DE", v)                   # cache at all: 21 T a pair
            c.push("DE")
            continue
        if v == ixval:
            c.push_ix()
            continue
        for r, held in regs.items():
            if held == v:
                c.push(r)
                break
        else:
            kill = next_kill(ops, i + 1)
            victim, far = None, -1
            for r in ("BC", "DE", "HL"):
                if regs[r] is None:
                    victim = r
                    break
                n = next_use(ops, i + 1, regs[r])
                if r == "HL":
                    n = min(n, kill)
                if n > far:
                    victim, far = r, n
            c.ld(victim, v)
            c.push(victim)
            regs[victim] = v


def pick_ix(lv):
    """IX holds one value for the whole level and is never reloaded."""
    vals = Counter(v for _, v in lv.pairs())
    return vals.most_common(1)[0][0] if vals else None


def rowsel(hpx, h):
    """Which source rows a height of h draws, bottom row first."""
    return [y * hpx // h for y in range(h)][::-1]


def build_dispatch(lv, org, h, window=True, cache=True, wevery=1):
    """A block a source row, plus the dispatcher and the row program."""
    ixval = pick_ix(lv)
    c = Code(org)
    entry = c.pc
    c.di()
    c.ld_nn_sp(SPSAVE)
    c.ld_iy_nn(SPSAVE)
    c.ld_ix(ixval)
    c.ld_sp_hl()
    c.exx()
    c._e(20, 0xED, 0x5B, *c.w(PROG))        # LD DE,(prog)
    jpfix = len(c.b)
    c.jp(0)
    disp = c.pc
    c.ld("HL", (lv.wb - 128) & 0xFFFF)
    c.add_hl_sp()
    if window:
        c.window()
    c.ld_sp_hl()
    c.ld_a_de()
    c.inc_e()
    c.ld_l_a()
    c.ld_a_de()
    c.inc_e()
    c.ld_h_a()
    c.jp_hl()
    c.b[jpfix + 1], c.b[jpfix + 2] = disp & 0xFF, disp >> 8
    exit_ = c.pc
    c.exx()
    c.ld_sp_nn(SPSAVE)
    c.ei()
    c.ret()
    blocks = {}
    for y in range(lv.hpx):
        blocks[y] = c.pc
        c.exx()
        emit_ops(c, ops_for_row(lv, y), ixval,
                 {"BC": None, "DE": None, "HL": None}, cache)
        c.exx()
        c.jp(disp)
    prog = [blocks[y] for y in rowsel(lv.hpx, h)] + [exit_]
    return c, entry, prog, ixval


def build_whole(lv, org, h, window=True, cache=True, wevery=1):
    """Every drawn row in one straight-line block, no dispatch."""
    ixval = pick_ix(lv)
    c = Code(org)
    entry = c.pc
    c.di()
    c.ld_nn_sp(SPSAVE)
    c.ld_iy_nn(SPSAVE)
    c.ld_ix(ixval)
    c.ld_sp_hl()
    ops = []
    sel = rowsel(lv.hpx, h)
    for n, y in enumerate(sel):
        ops += ops_for_row(lv, y)
        if n == len(sel) - 1:
            break
        step = lv.wb - 128
        if ops and ops[-1][0] == "skip":     # the left margin and the row
            step -= ops.pop()[1]             # step are one addition
        ops.append(("rowstep", step, window and n % wevery == 0))
    while ops and ops[-1][0] == "skip":
        ops.pop()
    emit_ops(c, ops, ixval, {"BC": None, "DE": None, "HL": None}, cache)
    c.ld_sp_nn(SPSAVE)
    c.ei()
    c.ret()
    return c, entry, None, ixval


def build_erase(lv, org, h, window=True, cache=True, wevery=1):
    """The same box filled with the background pair, bottom up."""
    c = Code(org)
    entry = c.pc
    c.di()
    c.ld_nn_sp(SPSAVE)
    c.ld_iy_nn(SPSAVE)
    c.ld("DE", (BG << 8) | BG)
    c.ld_sp_hl()
    for y in range(h):
        for _ in range(lv.wb // 2):
            c.push("DE")
        if y != h - 1:
            c.sp_add(lv.wb - 128, window and y % wevery == 0)
    c.ld_sp_nn(SPSAVE)
    c.ei()
    c.ret()
    return c, entry, None, None


SPSAVE = RUNTIME
PROG = RUNTIME + 2
PROGBUF = 0x0200


# ------------------------------------------------------------------ the bench

class Bench:
    def __init__(self):
        self.m = z80.Z80Machine()
        self.view = self.m.get_state_view()
        self.m.set_memory_block(HALTADDR, bytes([0x76]))
        self.m.set_breakpoint(HALTADDR)

    def poke(self, addr, data):
        self.m.set_memory_block(addr, bytes(data))

    def peek(self, addr, n):
        return bytes(self.view[44 + addr:44 + addr + n])

    def run(self, entry, hl):
        m = self.m
        self.poke(STACK, [HALTADDR & 0xFF, HALTADDR >> 8])
        m.sp = STACK
        m.hl = hl
        m.pc = entry
        m.halted = False
        total, prev = 0, m.frame_tick
        for _ in range(4000):
            m.ticks_to_stop = FRAME // 2
            m.run()
            step = m.frame_tick - prev
            total += step + FRAME if step < 0 else step
            prev = m.frame_tick
            if m.pc == HALTADDR:
                return total
        raise RuntimeError("did not return")


class Box:
    """A bare rectangle of background - what an erase has to put back.

    Rounded out to a whole pair, because a PUSH writes two bytes; the
    extra byte is backdrop over backdrop and costs nothing but itself.
    """

    def __init__(self, wb, h):
        wb += wb & 1
        self.wb = wb
        self.wpx = wb * 2
        self.hpx = h
        self.area = wb * h
        self.rows = [([BG] * wb, [True] * wb) for _ in range(h)]
        self.runs = [[(0, wb)] for _ in range(h)]


def backdrop():
    """A patterned screen, so a sprite drawn in the wrong place shows."""
    return bytes(((i * 37 + (i >> 7) * 11) & 0xFF) for i in range(SCRSIZE))


def model(lv, h, erase=False):
    """The screen the routine is supposed to leave."""
    scr = bytearray(backdrop())
    for dy, sy in enumerate(reversed(rowsel(lv.hpx, h))):
        by, _ = lv.rows[sy]
        base = (SPY + dy) * M.STRIDE + SPX
        if erase:
            for i in range(lv.wb):
                scr[base + i] = BG
            continue
        for s, e in lv.runs[sy]:
            for i in range(s, e):
                scr[base + i] = by[i]
    return bytes(scr)


def sp_init(lv, h, biased):
    bottom = SCREEN + (SPY + h - 1) * M.STRIDE + SPX + lv.wb
    return bottom + (128 - lv.wb) if biased else bottom


def measure(b, lv, h, kind, window=True, cache=True, wevery=1):
    org = CODE
    build = {"dispatch": build_dispatch, "whole": build_whole,
             "erase": build_erase}[kind]
    c, entry, prog, _ = build(lv, org, h, window, cache, wevery)
    b.poke(SCREEN, backdrop())
    b.poke(org, c.b)
    if prog is not None:
        b.poke(PROGBUF, b"".join(bytes([a & 0xFF, a >> 8]) for a in prog))
        b.poke(PROG, [PROGBUF & 0xFF, PROGBUF >> 8])
    t = b.run(entry, sp_init(lv, h, biased=(kind == "dispatch")))
    got = b.peek(SCREEN, SCRSIZE)
    want = model(lv, h, erase=(kind == "erase"))
    bad = sum(1 for i in range(SCRSIZE) if got[i] != want[i])
    return t, len(c.b), bad


def main():
    ch = M.chain()
    b = Bench()
    bad = [0]

    def run(lv, h, kind, **kw):
        t, size, e = measure(b, lv, h, kind, **kw)
        bad[0] += e
        return t, size

    print("A compiled 64x80 sprite and its chain, measured on the emulator.")
    print("6 MHz SAM, MODE 4, 120,000 T-states between 50 Hz interrupts.\n")

    print("  %-8s %6s %6s   %-19s %-19s %s"
          % ("", "box", "drawn", "silhouette, T-states", "opaque box, T-states",
             "erase"))
    print("  %-8s %6s %6s   %8s %10s %8s %10s %8s"
          % ("level", "bytes", "bytes", "dispatch", "whole", "dispatch",
             "whole", "box"))
    table = []
    for lv in ch:
        op = lv.opaque()
        h = lv.hpx
        sd, _ = run(lv, h, "dispatch")
        sw, _ = run(lv, h, "whole")
        od, _ = run(op, h, "dispatch")
        ow, _ = run(op, h, "whole")
        er, _ = run(lv, h, "erase")
        table.append((lv, sd, sw, od, ow, er))
        print("  %-8s %6d %6d   %8d %10d %8d %10d %8d"
              % ("%dx%d" % (lv.wpx, lv.hpx), lv.wb * lv.hpx, lv.area,
                 sd, sw, od, ow, er))

    print("\n  Two ways to keep a moving sprite clean, and what they cost.")
    print("  'silhouette' draws only the %d%%-odd of the box the sprite covers"
          % round(100 * ch[0].area / (ch[0].wb * ch[0].hpx)))
    print("  and puts the whole box back first; 'opaque' draws every byte of")
    print("  the box with the backdrop baked in, and only has to clear where")
    print("  the sprite has just left.\n")
    print("  %-8s %10s %9s %9s  %10s %9s %9s"
          % ("level", "silh+erase", "% frame", "a frame",
             "opaque", "% frame", "a frame"))
    for lv, sd, sw, od, ow, er in table:
        a, c2 = sw + er, ow
        print("  %-8s %10d %8.1f%% %9.1f  %10d %8.1f%% %9.1f"
              % ("%dx%d" % (lv.wpx, lv.hpx), a, 100.0 * a / 120000,
                 120000.0 / a, c2, 100.0 * c2 / 120000, 120000.0 / c2))

    print("\n  The top level at every height the row program can ask for")
    print("  (dispatch, silhouette) - the width is the level's, the height")
    print("  is free:")
    print("    %-8s %9s %8s %8s" % ("height", "T-states", "a row", "% frame"))
    for h in (80, 70, 60, 50, 40, 30, 20, 10):
        t, _ = run(ch[0], h, "dispatch")
        print("    %-8d %9d %8.1f %7.1f%%" % (h, t, t / h, 100.0 * t / 120000))

    print("\n  What the register cache is worth (whole, silhouette):")
    print("    %-8s %9s %9s %8s" % ("level", "cached", "LD+PUSH", "saved"))
    for lv in ch[:4]:
        t1, _ = run(lv, lv.hpx, "whole")
        t0, _ = run(lv, lv.hpx, "whole", cache=False)
        print("    %-8s %9d %9d %7.1f%%"
              % ("%dx%d" % (lv.wpx, lv.hpx), t1, t0, 100.0 * (t0 - t1) / t0))

    print("\n  What letting the interrupt in costs (a 22 T window a row):")
    print("    %-8s %9s %9s %8s" % ("level", "windows", "none", "cost"))
    for lv in ch[:4]:
        t1, _ = run(lv, lv.hpx, "whole", window=True)
        t0, _ = run(lv, lv.hpx, "whole", window=False)
        print("    %-8s %9d %9d %7.1f%%"
              % ("%dx%d" % (lv.wpx, lv.hpx), t1, t0, 100.0 * (t1 - t0) / t0))

    print("\n  Memory, one pose, one x phase:")
    disp = sum(len(build_dispatch(lv, CODE, lv.hpx)[0].b) for lv in ch)
    dispo = sum(len(build_dispatch(lv.opaque(), CODE, lv.hpx)[0].b)
                for lv in ch)
    whole = sum(len(build_whole(lv, CODE, lv.hpx)[0].b) for lv in ch)
    prog = sum(2 * lv.hpx + 2 for lv in ch)
    print("    %-44s %6d bytes" % ("the chain compiled, dispatch, silhouette",
                                   disp))
    print("    %-44s %6d" % ("the chain compiled, dispatch, opaque box", dispo))
    print("    %-44s %6d" % ("one row program a level, at full height", prog))
    print("    %-44s %6d" % ("the chain compiled whole, one height a level",
                             whole))
    print("    %-44s %6d" % ("the master and the levels, as bitmaps",
                             sum(lv.wb * lv.hpx for lv in ch)))

    def moving(lv):
        """Opaque box, a window every fourth row, plus the L the sprite
        leaves behind at 4 bytes across and 8 rows down a frame."""
        dx, dy = min(4, lv.wb), min(8, lv.hpx)
        t, _ = run(lv.opaque(), lv.hpx, "whole", wevery=4)
        a, _ = run(Box(dx, lv.hpx), lv.hpx, "erase", wevery=4)
        c2, _ = run(Box(lv.wb - dx, dy), dy, "erase", wevery=4)
        return t, a + c2

    print("\n  What a moving sprite still has to clear, drawn opaque: the")
    print("  L the old box leaves when the sprite has moved 4 bytes across")
    print("  and 8 rows down since this buffer was last drawn.")
    print("    %-8s %9s %9s %9s %8s"
          % ("level", "draw", "the L", "both", "% frame"))
    for lv in ch:
        t, l = moving(lv)
        print("    %-8s %9d %9d %9d %7.1f%%"
              % ("%dx%d" % (lv.wpx, lv.hpx), t, l, t + l,
                 100.0 * (t + l) / 120000))

    print("\n  A window every fourth row instead of every row (whole):")
    print("    %-8s %9s %9s %9s %8s"
          % ("level", "every row", "every 4th", "none", "DI held"))
    for lv in ch[:4]:
        t1, _ = run(lv.opaque(), lv.hpx, "whole", wevery=1)
        t4, _ = run(lv.opaque(), lv.hpx, "whole", wevery=4)
        t0, _ = run(lv.opaque(), lv.hpx, "whole", window=False)
        print("    %-8s %9d %9d %9d %6.0f us"
              % ("%dx%d" % (lv.wpx, lv.hpx), t1, t4, t0,
                 4.0 * t4 / lv.hpx / 6.0))

    print("\n  A scene, every sprite moving and clearing after itself:")
    tot = 0
    for idx, n in ((0, 1), (2, 2), (4, 4), (6, 8)):
        lv = ch[idx]
        t, l = moving(lv)
        tot += n * (t + l)
        print("    %-2d x %-8s %9d %8.1f%%"
              % (n, "%dx%d" % (lv.wpx, lv.hpx), n * (t + l),
                 100.0 * n * (t + l) / 120000))
    print("    %-13s %9d %8.1f%%" % ("15 sprites", tot, 100.0 * tot / 120000))
    print()
    print("    %-13s %9s %8s %9s" % ("all at", "each", "% frame", "a frame"))
    for lv in ch:
        t, l = moving(lv)
        print("    %-13s %9d %7.1f%% %9.1f"
              % ("%dx%d" % (lv.wpx, lv.hpx), t + l,
                 100.0 * (t + l) / 120000, 120000.0 / (t + l)))

    print("\n  %-46s %d" % ("screen bytes that differed from the model",
                             bad[0]))
    ok = bad[0] == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad[0]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
