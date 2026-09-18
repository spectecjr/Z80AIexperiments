#!/usr/bin/env python3
"""
sam.py - just enough SAM Coupe around tools/z80.py to run the prototype:
512K of RAM behind the two paging registers, the CLUT, the keyboard
matrix, and MODE 4 framebuffer decoding.

Paging follows the real thing: LMPR picks the page for section A and
section B is always A+1; HMPR does the same for C and D. VMPR picks the
displayed page, and the video hardware wraps into the next page when the
24K MODE 4 screen crosses the 16K boundary.
"""

PAGE = 16384
PAGES = 32                                     # 512K

P_CLUT, P_STAT, P_LMPR, P_HMPR, P_VMPR, P_KEYB = 248, 249, 250, 251, 252, 254

SCR_W, SCR_H, SCR_STRIDE = 256, 192, 128
SCR_BYTES = SCR_STRIDE * SCR_H


def clut_rgb(v):
    """SAM CLUT byte -> RGB.

    bit 6 GRN1  bit 5 RED1  bit 4 BLU1  bit 3 BRIGHT
    bit 2 GRN0  bit 1 RED0  bit 0 BLU0

    Two bits per channel plus one shared half-intensity bit, so each
    channel spans eight levels.
    """
    bright = (v >> 3) & 1
    def ch(hi, lo):
        level = (((v >> hi) & 1) << 2) | (((v >> lo) & 1) << 1) | bright
        return level * 255 // 7
    return ch(5, 1), ch(6, 2), ch(4, 0)        # R, G, B


class Sam:
    def __init__(self):
        self.ram = bytearray(PAGE * PAGES)
        self.clut = [0] * 16
        self.lmpr = 0
        self.hmpr = 0
        self.vmpr = 0
        self.border = 0
        self.keys = [0xFF] * 9                 # by row-select bit, active low
        self.base = [0, PAGE, 0, PAGE]
        self.repage()

    def repage(self):
        a = self.lmpr & 0x1F
        c = self.hmpr & 0x1F
        self.base = [a * PAGE, ((a + 1) % PAGES) * PAGE,
                     c * PAGE, ((c + 1) % PAGES) * PAGE]

    # ---- bus ----------------------------------------------------
    def rb(self, addr):
        return self.ram[self.base[addr >> 14] + (addr & 0x3FFF)]

    def wb(self, addr, v):
        self.ram[self.base[addr >> 14] + (addr & 0x3FFF)] = v

    def in_(self, port):
        low = port & 0xFF
        if low == P_KEYB:
            sel = (port >> 8) & 0xFF
            v = 0xFF
            for row in range(8):
                if not sel & (1 << row):
                    v &= self.keys[row]
            return v
        if low == P_STAT:
            return 0xFF                        # all interrupts inactive-high
        return 0xFF

    def out(self, port, v):
        low = port & 0xFF
        if low == P_CLUT:
            self.clut[(port >> 8) & 0x0F] = v & 0x7F
        elif low == P_LMPR:
            self.lmpr = v
            self.repage()
        elif low == P_HMPR:
            self.hmpr = v
            self.repage()
        elif low == P_VMPR:
            self.vmpr = v
        elif low == P_KEYB:
            self.border = v

    # ---- display ------------------------------------------------
    @property
    def screen_off(self):
        return bool(self.border & 0x80)

    def framebuffer(self):
        """Decode the displayed MODE 4 screen to a bytes of palette
        indices, 256x192, one byte per pixel."""
        out = bytearray(SCR_W * SCR_H)
        if self.screen_off:
            return bytes(out)
        start = (self.vmpr & 0x1F) * PAGE
        ram = self.ram
        o = 0
        for y in range(SCR_H):
            p = start + y * SCR_STRIDE
            row = ram[p:p + SCR_STRIDE]
            for b in row:
                out[o] = b >> 4
                out[o + 1] = b & 15
                o += 2
        return bytes(out)

    def palette(self):
        pal = []
        for v in self.clut:
            pal.extend(clut_rgb(v))
        return pal + [0] * (768 - len(pal))


class Machine:
    """Loads the prototype image into pages 0-1 and runs it frame by frame."""

    def __init__(self, image):
        from z80 import Z80
        self.sam = Sam()
        self.sam.ram[0:len(image)] = image
        self.cpu = Z80(self.sam)
        self.cpu.pc = 0x0000
        self.cpu.sp = 0x8000
        self.frames = 0
        self.instructions = 0

    def run_frame(self, cap=8_000_000):
        """One field: raise the frame interrupt, then run until the main
        loop parks itself on HALT again."""
        cpu = self.cpu
        cpu.interrupt()
        n = 0
        while not cpu.halted and n < cap:
            cpu.step()
            n += 1
        self.instructions += n
        self.frames += 1
        if n >= cap:
            raise RuntimeError("frame %d never reached HALT (pc=%04X)"
                               % (self.frames, cpu.pc))
        return n

    def boot(self, cap=40_000_000):
        """Run from reset until the main loop first reaches HALT."""
        cpu = self.cpu
        n = 0
        while not cpu.halted and n < cap:
            cpu.step()
            n += 1
        if n >= cap:
            raise RuntimeError("never reached the main loop (pc=%04X)" % cpu.pc)
        self.instructions += n
        return n
