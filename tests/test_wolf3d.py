#!/usr/bin/env python3
"""Verify and time wolf3d.z80s against tests/wolf.py.

Casts the maze on the Z80 and compares the column list against the
model, draws that list and compares every byte of the screen, and
times the whole frame. Runs it twice, once per viewport size, since
the geometry is generated and both are in the repo.

    pip install z80
    python3 tests/test_wolf3d.py
"""
import sys

from bench import Bench
import wolf

BUF = {0x80: 0x8000, 0x20: 0x2000}
VIEWS = [("harness_wolf.asm", 256, 144, 1),
         ("harness_wolf96.asm", 192, 96, 1),
         ("harness_wolfwide.asm", 256, 96, 2)]


def textures():
    def brick(base):
        t = bytearray(32 * 32)
        for u in range(32):
            for v in range(32):
                r = v // 8
                off = (u + (16 if r & 1 else 0)) % 16
                c = base + 2 if (off < 15 and v % 8 != 7) else base
                t[u * 32 + v] = (c << 4) | c
        return t

    def stone(base):
        t = bytearray(32 * 32)
        for u in range(32):
            for v in range(32):
                c = base + 1 if ((u * 7 + v * 13) % 11) < 6 else base + 3
                if (u % 16 == 0) or (v % 16 == 0):
                    c = base
                t[u * 32 + v] = (c << 4) | c
        return t
    return [brick(8), stone(1)]


POSES = ([(3 * 256 + 128, 3 * 256 + 128, a) for a in range(0, 256, 8)]
         + [(7 * 256 + 128, 1 * 256 + 128, a) for a in range(0, 256, 8)]
         + [(11 * 256 + 128, 11 * 256 + 128, a) for a in range(0, 256, 8)])


def run(harness, width, height, bpc):
    wolf.set_view(width, height, bpc)
    print("\n%dx%d, %d rays of %d pixels, %s"
          % (width, height, wolf.COLS, 2 * bpc, harness))
    b = Bench(harness, org=0)
    s = b.syms
    mp = list(b.peek(s["w3d_map"], 256))
    tex = textures()
    pages = [s["w3d_tex1"] >> 8, s["w3d_tex2"] >> 8]
    ceil = b.peek(s["w3d_ceil"], 1)[0]
    floor = b.peek(s["w3d_floor"], 1)[0]
    it, _ = b.call_regs(s["w3d_init"])
    end = int.from_bytes(b.peek(s["w3d_gp"], 2), "little")
    ceiling = s["qsmul8"]
    print("  w3d_init  %d T-states once, for %d bytes of scaler, %d to spare"
          % (it, end - 0xE000, ceiling - end))
    bad = 0
    if end > ceiling:
        print("  SCALER BANK OVERRUN: ends %04X, %04X is spoken for"
              % (end, ceiling))
        bad += 1

    times, ctimes, ftimes, wallbytes = [], [], [], []
    for px, py, ang in POSES:
        cols = wolf.frame(mp, px, py, ang)
        raw = bytearray()
        wb = 0
        for c in cols:
            h, cell, u, side = c
            raw += bytes([h, pages[cell - 1], u])
            wb += wolf.rung(h)[1] * wolf.BPC
        wallbytes.append(wb)

        # the caster, against the model's own ray casting
        b.poke(s["w3d_px"], (px & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["w3d_py"], (py & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["w3d_ang"], bytes([ang]))
        b.poke(s["w3d_cols"], bytes(3 * wolf.COLS))
        t, _ = b.call_regs(s["w3d_cast"])
        ctimes.append(t)
        got = b.peek(s["w3d_cols"], 3 * wolf.COLS)
        if got != bytes(raw):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(raw)) if got[i] != raw[i]]
                print("  CAST MISMATCH at (%d,%d) angle %d: %d of %d bytes, "
                      "first column %d field %d, got %d want %d"
                      % (px, py, ang, len(d), len(raw), d[0] // 3, d[0] % 3,
                         got[d[0]], raw[d[0]]))

        # and the renderer, against the model's own drawing
        b.poke(s["w3d_cols"], bytes(raw))
        into = b.peek(s["w3d_back"], 1)[0]
        t, _ = b.call_regs(s["w3d_draw"])
        times.append(t)
        want = wolf.draw(cols, tex, ceil, floor)
        got = b.peek(BUF[into], wolf.STRIDE * wolf.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  DRAW MISMATCH at (%d,%d) angle %d: %d bytes, first "
                      "at %d (y=%d x=%d) got %02X want %02X"
                      % (px, py, ang, len(d), d[0], d[0] // wolf.STRIDE,
                         (d[0] % wolf.STRIDE) * 2, got[d[0]], want[d[0]]))
        t, _ = b.call_regs(s["w3d_frame"])
        ftimes.append(t)

    n = len(POSES)
    wb = sum(wallbytes) / n
    pt, _ = b.call_regs(s["w3d_prefill"])
    print("  %-40s %4d poses, %d mismatches"
          % ("Z80 against the model, cast and drawn", n, bad))
    print("  %-40s %d..%d, mean %.0f"
          % ("wall bytes a frame", min(wallbytes), max(wallbytes), wb))
    print("  w3d_cast     min %7d  mean %7.0f  max %7d   %.0f T a ray"
          % (min(ctimes), sum(ctimes) / n, max(ctimes),
             sum(ctimes) / n / wolf.COLS))
    print("  w3d_draw     min %7d  mean %7.0f  max %7d   %.1f T a wall byte"
          % (min(times), sum(times) / n, max(times),
             (sum(times) / n - pt) / wb))
    print("  w3d_prefill      %7d              of that      %.1f T a byte"
          % (pt, pt / (wolf.BYTES * wolf.VH)))
    fm = sum(ftimes) / n
    print("  w3d_frame    min %7d  mean %7.0f  max %7d"
          % (min(ftimes), fm, max(ftimes)))
    print("  %-40s %.1f Hz mean, %.1f Hz worst"
          % ("which at 6 MHz is", 6e6 / fm, 6e6 / max(ftimes)))
    print("  %-40s %.1f Hz mean, %.1f Hz worst"
          % ("and on a 50 Hz display, vsynced", 50 / vs(fm), 50 / vs(max(ftimes))))
    return bad


def vs(t):
    """Display frames one rendered frame takes, waiting for the flyback."""
    return -(-int(t) // 120000)         # 6 MHz / 50 Hz


def main():
    bad = sum(run(*v) for v in VIEWS)
    print("\n%s" % ("ALL TESTS PASSED" if not bad else "FAILURES: %d" % bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
