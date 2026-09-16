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

which is what a MODE 4 screen leaves: 24K of a 32K pair.
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
                 code_at=0xE000, ram=256 * 1024, here=None, root=None,
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
        for i, s in enumerate(screens):                 # a copy behind each
            at = (s + 1) * PAGE + (code_at & 0x3FFF)    # buffer, as the
            self.ram[at:at + len(img)] = img            # routine requires
        for i, h in enumerate(chunks):
            img, syms = assemble(h, here=here, root=root, defines=defs)
            self.ram[2 * i * PAGE:2 * i * PAGE + len(img)] = img
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
