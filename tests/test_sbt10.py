#!/usr/bin/env python3
"""Run build/chequer10.sbt the way a machine would, and check what it draws.

    python3 tests/test_sbt10.py

`tests/sam.py` calls a routine: it assembles the map itself, sets the
paging registers and pokes the state. This runs the SHIPPED IMAGE
instead - the file SimCoupe boots - from the entry state the ROM leaves
(`LMPR = 0x1F`, `HMPR = 1`, called at 0x8000) and with nothing poked at
all. Everything the demo needs, the image has to do for itself: move
its own pages into the map, put the resident block behind both
buffers, set the palette, play the flight path.

What it checks, in order of how much it would hurt to get wrong:

  the map      every chunk where `tests/sam.py` puts it, after the
               loader has moved it there
  the picture  the displayed buffer against `tests/chequer10.py`, the
               same model the bench test compares against, for frames
               of the path
  the palette  the sixteen CLUT entries the demo writes

The frame interrupt is modelled, because the demo's pacing polls for
it: a frame is 119,808 T-states and the bit is low for 128 of them.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("HARRIER_MINP", "1")
os.environ.setdefault("HARRIER_HZ", "95")
os.environ.setdefault("HARRIER_CAMH", "308")
os.environ.setdefault("DESERT_ROWS", "20")
os.environ.setdefault("HARRIER_SKY", "15")
os.environ.setdefault("DESERT_SKY", "15")
os.environ.setdefault("JET_W", "24")
os.environ.setdefault("JET_H", "48")
os.environ.setdefault("CHQ_SWAP", "0xBB")
os.environ.setdefault("JET_PAL", "board4")
os.environ.setdefault("DESERT_PAL", "board4")

import z80                                              # noqa: E402
from bench import MEMOFF, FRAME                         # noqa: E402
from sam import PAGE, SCREEN, LMPR, HMPR, VMPR          # noqa: E402

FRAME_T = 119808                # a display frame on a 6 MHz SAM
INT_T = 128                     # and how long its interrupt is active
STATUS = 0xF9
KEYS = 0xFE


class Machine:
    """A SAM with the image loaded, entered the way the ROM enters it."""

    def __init__(self, image, ram=512 * 1024):
        self.ram = bytearray(ram)
        self.ram[PAGE:PAGE + len(image)] = image        # LOAD CODE 32768
        self.clut = [0] * 16
        self.line = 255
        self.m = z80.Z80Machine()
        self.view = self.m.get_state_view()
        self.mapped = {0x0000: None, 0x8000: None}
        self.lmpr, self.hmpr, self.vmpr = 0x1F, 0x01, 0x00
        self.m.set_output_callback(self._out)
        self.m.set_input_callback(self._in)
        self._map(0x0000, 31)                           # LMPR 0x1F: page 31
        self._map(0x8000, 1)                            # and page 1 above
        self.m.pc = 0x8000
        self.m.sp = 0x7F00
        self.t = 0
        self.tick0 = self.m.frame_tick
        self.ints = True                                # deliver interrupts
        self.taken = 0

    # --- paging, the same rule tests/sam.py follows ------------------

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
        elif port == 0xF8:
            self.clut[(addr >> 8) & 15] = value & 127
        elif port == STATUS:
            self.line = value

    def _in(self, addr):
        port = addr & 0xFF
        if port == LMPR:
            return self.lmpr
        if port == HMPR:
            return self.hmpr
        if port == VMPR:
            return self.vmpr
        if port == STATUS:                              # the frame interrupt,
            phase = self.now() % FRAME_T                # active low for 128
            return 0xF7 if phase < INT_T else 0xFF      # T-states a frame, low
        if port == KEYS:
            return 0xFF                                 # nothing pressed
        return 0xFF

    def _map(self, base, page):
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

    # --- running it -------------------------------------------------

    def now(self):
        """T-states since the machine started, mid-slice included.

        The demo polls the status port for the frame interrupt, so the
        clock has to move while the emulator is inside a run - not just
        between runs, which would leave the bit stuck at whatever it
        was when the slice began.
        """
        d = self.m.frame_tick - self.tick0
        return self.t + (d + FRAME if d < 0 else d)

    def slice(self, ticks):
        """Run one stretch, keeping the clock across the counter's wrap."""
        self.tick0 = self.m.frame_tick
        self.m.ticks_to_stop = max(1, ticks)
        self.m.run()
        d = self.m.frame_tick - self.tick0
        d += FRAME if d < 0 else 0
        self.t += d
        self.tick0 = self.m.frame_tick      # so that now() outside a run
        return d                            # does not count d a second time

    def run(self, ticks):
        """Run, taking the frame interrupt the way the machine offers it.

        The demo polls for the interrupt rather than taking it, but it
        cannot stop it being offered: its own routines EI after every
        stretch that puts SP on the screen. So the interrupt is
        delivered here too - held out for the 128 T-states it is active
        and dropped if the CPU never enables interrupts inside that,
        which is exactly what a SAM does.
        """
        left = ticks
        while left > 0 and not self.m.halted:
            phase = self.now() % FRAME_T
            if phase < INT_T:                   # inside the active window
                if self.m.iff1 and self.ints:
                    self.m.on_handle_active_int()
                    self.taken += 1
                left -= self.slice(min(left, 32))
            else:
                left -= self.slice(min(left, FRAME_T - phase, FRAME // 2))
        return ticks - max(0, left)

    def page(self, p):
        """A page of RAM, whether or not it happens to be mapped."""
        self._out_block(0x0000)
        self._out_block(0x8000)
        return bytes(self.ram[p * PAGE:(p + 1) * PAGE])

    def screen(self):
        """The buffer the video hardware is showing."""
        p = self.vmpr & 31
        self._out_block(0x0000)
        self._out_block(0x8000)
        return bytes(self.ram[p * PAGE:p * PAGE + SCREEN])


def frames(b, want, limit=60_000_000):
    """Run until each flip and hand back what the screen then holds.

    The first VMPR write is not a flip: `chq4_init` points the video
    hardware at one buffer while it fills the other, so it is thrown
    away here and the frames of the flight start after it.
    """
    out, shown = [], b.vmpr & 31
    spent, first = 0, True
    while len(out) < want and spent < limit:
        spent += b.run(4_000)           # fine enough to time a flip
        if (b.vmpr & 31) != shown:
            shown = b.vmpr & 31
            if first:
                first = False           # cq10_init's, not a frame's
                continue
            out.append((b.now(), b.screen()))
    return out


def contention(script, every=17):
    """What a frame costs once the ASIC has had its cycles.

    `costs.md` numbers are the bench's, which has no contention; this
    prices the same frames through `tests/sam.py`'s model - SimCoupe's
    rules, confirmed against the machine by `contend.z80s` - and that
    is what decides how many display frames the demo holds each one
    for.
    """
    from sam import Sam
    from mksbt10 import CHUNKS, SCREENS
    b = Sam("harness_chq10.asm", CHUNKS, screens=SCREENS,
            chunk_defines=lambda y: {"CHQ4_RET": y["chq4_ret"],
                                     "CHQ4_SCR": y["CHQ4_SCREEN"],
                                     "C9_RET": y["c9_ret"],
                                     "CQ9_R": y["cq10_pret"],
                                     "CQ10_R": y["cq10_ret"]})
    s = b.syms
    b.call(s["cq10_init"])
    out = []
    for i in range(0, len(script), every):
        camx, camz, hz, px, py, pose, tk, tx, ty = script[i]
        for _ in range(2):              # both buffers, so the sprite boxes
            b.poke(s["chq4_camx"], camx.to_bytes(2, "little"))
            b.poke(s["chq4_camz"], camz.to_bytes(2, "little"))
            b.poke(s["cq10_hz"], bytes([hz]))
            b.poke(s["cq10_px"], bytes([px]))
            b.poke(s["cq10_py"], bytes([py]))
            b.poke(s["cq10_pose"], bytes([pose]))
            b.poke(s["cq10_tk"], bytes(tk))
            b.poke(s["cq10_tx"], bytes(tx))
            b.poke(s["cq10_ty"], bytes(ty))
            nat, con, _, _ = b.contended(s["cq10_frame"])
        out.append((nat, con))
    lo = min(c for _, c in out)
    hi = max(c for _, c in out)
    print("  %-40s %d to %d T-states, x%.2f"
          % ("a frame, contended", lo, hi,
             sum(c / n for n, c in out) / len(out)))
    print("  %-40s %.1f to %.1f, so %.1f Hz down to %.1f"
          % ("display frames it is held for", lo / FRAME_T, hi / FRAME_T,
             50 / max(1, round(lo / FRAME_T + 0.49)),
             50 / max(1, round(hi / FRAME_T + 0.49))))
    return out


def main():
    from mksbt10 import build, pages_for, CHUNKS, SCREENS
    from mkdemo10 import palette, path as flight
    from bench import assemble
    import chequer10 as C

    path, syms = build(quiet=True)
    image = open(path, "rb").read()
    print("  %-40s %7d bytes, %d pages, entered at 0x8000"
          % (os.path.basename(path), len(image), len(image) // PAGE))

    b = Machine(image)
    script = flight()
    shots = frames(b, 6)                # the moves, cq10_init, and frames
    bad = 0

    defs = {"CHQ4_RET": syms["chq4_ret"], "CHQ4_SCR": syms["CHQ4_SCREEN"],
            "C9_RET": syms["c9_ret"], "CQ9_R": syms["cq10_pret"],
            "CQ10_R": syms["cq10_ret"]}
    pages = pages_for(CHUNKS, SCREENS)
    for h, p in zip(CHUNKS, pages):
        img, _ = assemble(h, defines=defs)
        got = b.page(p) + b.page(p + 1)
        if got[:len(img)] != img:
            bad += 1
            n = next(i for i in range(len(img)) if got[i] != img[i])
            print("  MAP: %s is not at page %d, from byte %d" % (h, p, n))
    print("  %-40s %d chunks, %d wrong, where tests/sam.py puts them"
          % ("the map the loader assembled", len(CHUNKS), bad))

    want = palette()
    wrong = sum(1 for i in range(16) if b.clut[i] != want[i])
    bad += wrong
    print("  %-40s 16 entries, %d wrong" % ("the palette it wrote", wrong))

    miss = 0
    for i, (at, got) in enumerate(shots):
        camx, camz, hz, px, py, pose, tk, tx, ty = script[i]
        trees = [(tk[j], tx[j], ty[j]) for j in range(len(tk))]
        w = bytes(C.frame(camx - 0x10000 if camx > 0x7FFF else camx,
                          camz, hz, px, py, pose, trees))
        if got[:len(w)] != w:
            miss += 1
            n = next(k for k in range(len(w)) if got[k] != w[k])
            print("  FRAME %d: %d bytes differ, first at %d (row %d)"
                  % (i, sum(1 for k in range(len(w)) if got[k] != w[k]),
                     n, n // 128))
    bad += miss
    print("  %-40s %d frames of the flight, %d wrong"
          % ("the picture against the model", len(shots), miss))
    if len(shots) >= 2:
        cost = (shots[-1][0] - shots[0][0]) // (len(shots) - 1)
        print("  %-40s %d T-states a frame, %.1f display frames"
              % ("flip to flip, uncontended", cost, cost / FRAME_T))
    print()
    contention(script)
    print()
    print("ALL TESTS PASSED" if not bad else "%d checks failed" % bad)
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
