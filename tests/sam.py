"""The Coupé's memory paging, for the bench.

The `z80` module the bench drives is a flat 64K, which is the Z80's view
and not the machine's: a SAM has 256K in 16K pages, and LMPR (250) and
HMPR (251) each map a *pair* of them - the page written and the one
above it - into the low and high 32K. VMPR (252) points the video
hardware at a page of its own, which is why the displayed buffer needs
no mapping at all.

So this keeps physical RAM as a bytearray and emulates the three
registers through the machine's output callback: on a write to LMPR or
HMPR the 32K that was there is copied back and the new pair copied in.
The T-state counts stay honest, because the `OUT` is really executed -
all that happens on the Python side is memory moving where the ASIC
would have moved it.

The map is road2's (see road2.z80s):

    pages 0,1   chunk 0 of the run bank, and the caller's stack at 7FFE
    pages 2,3   chunk 1
    pages 4,5   buffer 0, and the resident code in page 5's spare 8K
    pages 6,7   buffer 1, and a second copy of the resident code

which is what a MODE 4 screen leaves: 24K of a 32K pair. Chunks are laid
out two pages at a time from page 0 and step over the buffers, so
chequer8's eight are at 0, 2, 4, 6, 8, 14, 16 and 18.

The machine here is a 512K one, which is what the paging registers can
address: five bits of page, 32 pages, 512K. A 256K SAM has sixteen
pages and every one of them is spoken for by the time chequer7's board,
buffers and pilot are in - so chequer8's desert is the point at which
these demos stop fitting a base machine, and chequer8.md says what a
256K version would have to give up.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import z80                                              # noqa: E402
from bench import assemble, FRAME, MEMOFF               # noqa: E402

PAGE = 0x4000
LMPR, HMPR, VMPR = 250, 251, 252
SCREEN = 24576
RETADDR = 0x7FFF                # a HALT at the top of chunk 0, under the
STACK = 0x7FF0                  # caller's stack, which lives there because
                                # it is the one block the routine leaves
                                # alone and puts back


class Sam:
    def __init__(self, resident, chunks, code_page=5, screens=(4, 6),
                 code_at=0xE000, ram=512 * 1024, here=None, root=None,
                 chunk_defines=None):
        """resident goes behind each screen; chunks at pages 0, 2, 4 ...

        chunk_defines, if given, is called with the resident's symbols
        and returns assembler defines for the chunks - which is how a
        chunk learns the one address it needs from the code, without the
        code having to sit at a fixed one.
        """
        self.ram = bytearray(ram)
        img, self.syms = assemble(resident, here=here, root=root)
        defs = chunk_defines(self.syms) if chunk_defines else None
        self.screens = screens
        self.resident = len(img)        # what the map is actually holding,
        self.bank = []                  # for the memory report below
        for i, s in enumerate(screens):                 # a copy behind each
            at = (s + 1) * PAGE + (code_at & 0x3FFF)    # buffer, as the
            self.ram[at:at + len(img)] = img            # routine requires
        self.pages = []                                 # chunks go two
        taken, p = set(), 0                             # pages at a time,
        for s in screens:                               # round the buffers
            taken |= {s, s + 1}
        while len(self.pages) < len(chunks):
            if p not in taken and p + 1 not in taken:
                self.pages.append(p)
            p += 2
        for h, p in zip(chunks, self.pages):
            img, syms = assemble(h, here=here, root=root, defines=defs)
            if (p + 2) * PAGE > len(self.ram):
                raise SystemExit("%s wants pages %d and %d, and this "
                                 "machine has %d"
                                 % (h, p, p + 1, len(self.ram) // PAGE))
            self.ram[p * PAGE:p * PAGE + len(img)] = img
            self.bank.append((h, len(img)))
            self.syms.update(syms)
        self.ram[RETADDR] = 0x76                        # HALT, to return to

        self.m = z80.Z80Machine()
        self.view = self.m.get_state_view()
        self.mapped = {0x0000: None, 0x8000: None}
        self.lmpr, self.hmpr, self.vmpr = 0x20, screens[0], 0
        self.m.set_output_callback(self._out)
        self.m.set_input_callback(self._in)
        self._map(0x0000, 0)
        self._map(0x8000, screens[0])
        self.m.set_breakpoint(RETADDR)

    # --- what it all takes -----------------------------------------

    def memory(self):
        """What the map holds and what it claims, in bytes and in pages.

        The two are not the same and the difference is the point: a
        chunk gets a *pair* of pages because that is what LMPR maps, so
        a bank of eleven chunks claims 352K however much of it is
        compiled code. The resident block is counted once per buffer,
        because there really is a copy behind each.
        """
        bank = sum(n for _, n in self.bank)
        code = self.resident * len(self.screens)
        screens = SCREEN * len(self.screens)
        pages = 2 * len(self.bank) + 2 * len(self.screens)
        return {"bank": bank, "chunks": len(self.bank),
                "resident": self.resident, "code": code,
                "screens": screens, "held": bank + code + screens,
                "pages": pages, "claimed": pages * PAGE}

    def report_memory(self, indent="  ", detail=True):
        """The memory report the tests print."""
        m = self.memory()
        print("%s%-40s %7d bytes in %d pages (%dK of a %dK machine)"
              % (indent, "memory", m["held"], m["pages"],
                 m["claimed"] // 1024, len(self.ram) // 1024))
        print("%s%-40s %7d bytes over %d pages"
              % (indent, "  the bank, %d chunks" % m["chunks"],
                 m["bank"], 2 * m["chunks"]))
        if detail:
            for (h, n), p in zip(self.bank, self.pages):
                name = h.replace("harness_", "").replace(".asm", "")
                print("%s%-40s %7d bytes  (%3d%% of its pair)"
                      % (indent, "    %-14s pages %2d,%2d"
                         % (name, p, p + 1), n, round(100 * n / (2 * PAGE))))
        print("%s%-40s %7d bytes, a copy behind each buffer"
              % (indent, "  the resident block, %d bytes" % m["resident"],
                 m["code"]))
        print("%s%-40s %7d bytes in %d pages"
              % (indent, "  the buffers", m["screens"],
                 2 * len(self.screens)))
        return m

    # --- the three registers ---------------------------------------

    def _out(self, addr, value):
        port = addr & 0xFF
        if port == LMPR:
            self.lmpr = value
            self._map(0x0000, value & 31)
        elif port == HMPR:
            self.hmpr = value
            self._map(0x8000, value & 31)
        elif port == VMPR:
            self.vmpr = value

    def _in(self, addr):
        return {LMPR: self.lmpr, HMPR: self.hmpr,
                VMPR: self.vmpr}.get(addr & 0xFF, 0xFF)

    def _map(self, base, page):
        """Put a pair of pages in a block, writing back what was there."""
        if self.mapped[base] == page:
            return
        self._out_block(base)
        pair = bytearray()
        for i in (0, 1):
            p = (page + i) & 31
            pair += self.ram[p * PAGE:(p + 1) * PAGE]
        self.m.set_memory_block(base, bytes(pair))
        self.mapped[base] = page

    def _out_block(self, base):
        page = self.mapped[base]
        if page is None:
            return
        for i in (0, 1):
            p = (page + i) & 31
            self.ram[p * PAGE:(p + 1) * PAGE] = bytes(
                self.view[MEMOFF + base + i * PAGE:
                          MEMOFF + base + (i + 1) * PAGE])

    # --- memory, mapped and not ------------------------------------

    def poke(self, addr, data):
        self.m.set_memory_block(addr, bytes(data))

    def peek(self, addr, n):
        return bytes(self.view[MEMOFF + addr:MEMOFF + addr + n])

    def screen(self, page):
        """A buffer, whether or not it happens to be mapped."""
        self._out_block(0x0000)
        self._out_block(0x8000)
        return bytes(self.ram[page * PAGE:page * PAGE + SCREEN])

    def shown(self):
        """The buffer the video hardware is displaying."""
        return self.vmpr & 31

    # --- calling ---------------------------------------------------

    def traffic(self, entry):
        """One call, with every memory cycle it takes counted.

        Contention on a real SAM is paid per memory ACCESS rather than
        per T-state: the ASIC is fetching the display out of the same
        DRAM, and a routine that spends its time in registers loses less
        to it than one that spends its time in PUSH. Nothing here models
        the contention - that wants rules this repo has not got - but
        the traffic it would be charged on is measurable, and it is the
        half of the sum that depends on the code rather than on the
        machine.

        Reads include every opcode fetch, because the bus does not care
        why it was busy. Returns (T-states, reads, writes, and how many
        of the writes landed on the screen).
        """
        m, view = self.m, self.view
        lo, hi = 0x8000, 0x8000 + SCREEN        # the back buffer, mapped
        n = [0, 0, 0]

        def rd(addr):
            n[0] += 1
            return view[MEMOFF + addr]

        def wr(addr, value):
            n[1] += 1
            if lo <= addr < hi:
                n[2] += 1
            view[MEMOFF + addr] = value
            return 0

        marks = z80.Z80Machine.READ_MARK | z80.Z80Machine.WRITE_MARK
        m.set_read_callback(rd)
        m.set_write_callback(wr)
        m.mark_addrs(0, 0x10000, marks)
        try:
            t = self.call(entry)
        finally:
            m.unmark_addrs(0, 0x10000, marks)   # and back to full speed:
        return (t,) + tuple(n)                  # a marked access is a
                                                # call into Python

    # SimCoupe's wait-state rules (Base/Memory.cpp, Base/SAMIO.h), applied
    # to our own runs. The two line up exactly: SimCoupe computes its delay
    # from `frame_cycles + 2` at the start of the machine cycle, and this
    # module's access callbacks fire exactly 2 T-states into it - so the
    # `t` a callback sees IS SimCoupe's `t + 2`.
    T_LINE, LINES, SIDE, TOP, SCREEN_LINES = 384, 312, 64, 68, 192
    FRAME_T = T_LINE * LINES                    # 119,808
    SLOTS = 23808                               # and what it grants

    @classmethod
    def _mem_wait(cls, t, screen_on=True):
        """The wait before a memory access at absolute frame cycle t."""
        t %= cls.FRAME_T
        line, lc = t // cls.T_LINE, (t + 4) % cls.T_LINE
        main = (screen_on and cls.TOP <= line < cls.TOP + cls.SCREEN_LINES
                and lc >= 2 * cls.SIDE)
        mask = 7 if main else 3
        return mask - (t & mask)

    @classmethod
    def _port_wait(cls, t, port):
        """And before a port access - the ASIC's ports are 248 and above,
        and they wait for an 8 T boundary wherever the raster is."""
        if (port & 0xFF) < 0xF8:
            return 0
        return 7 - ((t % cls.FRAME_T) & 7)

    def contended(self, entry, start=0, screen_on=True):
        """One call, with the SAM's wait states counted into the clock.

        `start` is the frame cycle the routine begins at - 0 is the frame
        interrupt, and the display does not start until line 68. The
        instruction stream cannot change with timing here (these routines
        run DI from end to end), so the accesses are the same ones; what
        moves is when each of them happens, and this tracks that.

        Returns (natural T, contended T, accesses, waits).
        """
        m, view = self.m, self.view
        st = {"t": start, "prev": 0, "wait": 0, "n": 0}

        def clock(nat):
            """The contended frame cycle for a natural tick count."""
            step = nat - st["prev"]
            if step < 0:
                step += FRAME
            st["prev"] = nat
            st["t"] += step
            return st["t"]

        def rd(addr):
            st["n"] += 1
            w = self._mem_wait(clock(m.frame_tick), screen_on)
            st["wait"] += w
            st["t"] += w
            return view[MEMOFF + addr]

        def wr(addr, value):
            st["n"] += 1
            w = self._mem_wait(clock(m.frame_tick), screen_on)
            st["wait"] += w
            st["t"] += w
            view[MEMOFF + addr] = value
            return 0

        def out(addr, value):
            w = self._port_wait(clock(m.frame_tick), addr)
            st["wait"] += w
            st["t"] += w
            self._out(addr, value)

        def inp(addr):
            w = self._port_wait(clock(m.frame_tick), addr)
            st["wait"] += w
            st["t"] += w
            return self._in(addr)

        marks = z80.Z80Machine.READ_MARK | z80.Z80Machine.WRITE_MARK
        m.set_read_callback(rd)
        m.set_write_callback(wr)
        m.set_output_callback(out)
        m.set_input_callback(inp)
        m.mark_addrs(0, 0x10000, marks)
        try:
            st["prev"] = m.frame_tick
            t = self.call(entry)
        finally:
            m.unmark_addrs(0, 0x10000, marks)
            m.set_output_callback(self._out)
            m.set_input_callback(self._in)
        return t, t + st["wait"], st["n"], st["wait"]

    def call(self, entry):
        """T-states for one call, stopping on the HALT at RETADDR."""
        m = self.m
        m.sp = STACK
        self.poke(STACK, RETADDR.to_bytes(2, "little"))
        m.pc = entry
        m.halted = False
        total, prev = 0, m.frame_tick
        for _ in range(4000):
            m.ticks_to_stop = FRAME // 2
            m.run()
            step = m.frame_tick - prev
            total += step + FRAME if step < 0 else step
            prev = m.frame_tick
            if m.pc == RETADDR:
                return total
        raise RuntimeError("routine did not return (runaway loop?)")
