#!/usr/bin/env python3
"""Verify and time wolf3d.z80s against tests/wolf.py.

Feeds the Z80 the column list the model casts, draws it, and compares
every byte of the viewport.

    pip install z80
    python3 tests/test_wolf3d.py
"""
import sys

from bench import Bench
import wolf

BUF = {0x80: 0x8000, 0x20: 0x2000}


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


def main():
    b = Bench("harness_wolf.asm", org=0)
    s = b.syms
    mp = list(b.peek(s["w3d_map"], 256))
    tex = textures()
    pages = [s["w3d_tex1"] >> 8, s["w3d_tex2"] >> 8]
    ceil = b.peek(s["w3d_ceil"], 1)[0]
    floor = b.peek(s["w3d_floor"], 1)[0]
    it, _ = b.call_regs(s["w3d_init"])
    print("  w3d_init (both buffers blacked, scalers built)  %d T-states" % it)
    used = int.from_bytes(b.peek(s["w3d_gp"], 2), "little") - 0xE000
    print("  scaler bank                                    %d bytes" % used)

    poses = [(3 * 256 + 128, 3 * 256 + 128, a) for a in range(0, 256, 8)]
    poses += [(7 * 256 + 128, 1 * 256 + 128, a) for a in range(0, 256, 8)]
    poses += [(11 * 256 + 128, 11 * 256 + 128, a) for a in range(0, 256, 8)]
    bad = 0
    times = []
    wallbytes = []
    shown = None
    for px, py, ang in poses:
        cols = wolf.frame(mp, px, py, ang)
        raw = bytearray()
        wb = 0
        for c in cols:
            if c is None:
                raw += bytes([0, 0, 0])
            else:
                h, cell, u, side = c
                raw += bytes([h, pages[cell - 1], u])
                wb += wolf.rung(h)[1]
        b.poke(s["w3d_cols"], bytes(raw))
        wallbytes.append(wb)
        into = b.peek(s["w3d_back"], 1)[0]
        t, _ = b.call_regs(s["w3d_draw"])
        times.append(t)
        want = wolf.draw(cols, tex, ceil, floor)
        got = b.peek(BUF[into], wolf.STRIDE * wolf.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                diff = [i for i in range(len(want)) if got[i] != want[i]]
                print("  MISMATCH at (%d,%d) angle %d: %d bytes, first at %d "
                      "(y=%d x=%d) got %02X want %02X"
                      % (px, py, ang, len(diff), diff[0],
                         diff[0] // wolf.STRIDE, (diff[0] % wolf.STRIDE) * 2,
                         got[diff[0]], want[diff[0]]))
        elif shown is None:
            shown = got
    print("  %-40s %4d poses, %d mismatches"
          % ("Z80 buffer against the model", len(poses), bad))

    cbad = 0
    ctimes = []
    for px, py, ang in poses:
        want = bytearray()
        for c in wolf.frame(mp, px, py, ang):
            h, cell, u, side = c
            want += bytes([h, pages[cell - 1], u])
        b.poke(s["w3d_px"], (px & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["w3d_py"], (py & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["w3d_ang"], bytes([ang]))
        b.poke(s["w3d_cols"], bytes(3 * wolf.COLS))
        t, _ = b.call_regs(s["w3d_cast"])
        ctimes.append(t)
        got = b.peek(s["w3d_cols"], 3 * wolf.COLS)
        if got != bytes(want):
            cbad += 1
            if cbad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  MISMATCH at (%d,%d) angle %d: %d of %d bytes, "
                      "first column %d field %d, got %d want %d"
                      % (px, py, ang, len(d), len(want), d[0] // 3, d[0] % 3,
                         got[d[0]], want[d[0]]))
    print("  %-40s %4d poses, %d mismatches"
          % ("Z80 column list against the model", len(poses), cbad))
    bad += cbad
    print("  %-40s %d..%d, mean %d"
          % ("wall bytes a frame", min(wallbytes), max(wallbytes),
             sum(wallbytes) / len(wallbytes)))
    print()
    print("  w3d_draw     min %d T-states, mean %.0f, max %d"
          % (min(times), sum(times) / len(times), max(times)))
    pt, _ = b.call_regs(s["w3d_prefill"])
    print("  w3d_prefill  %d T-states of that" % pt)
    mean = sum(times) / len(times)
    print("  %-40s %.1f T a wall byte"
          % ("so the wall columns cost",
             (mean - pt) / (sum(wallbytes) / len(wallbytes))))
    print("  w3d_cast     min %d T-states, mean %.0f, max %d"
          % (min(ctimes), sum(ctimes) / len(ctimes), max(ctimes)))
    print("               %.0f T-states a ray"
          % (sum(ctimes) / len(ctimes) / wolf.COLS))
    ftimes = []
    for px, py, ang in poses[::4]:
        b.poke(s["w3d_px"], (px & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["w3d_py"], (py & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["w3d_ang"], bytes([ang]))
        t, _ = b.call_regs(s["w3d_frame"])
        ftimes.append(t)
    fm = sum(ftimes) / len(ftimes)
    print("  w3d_frame    min %d T-states, mean %.0f, max %d"
          % (min(ftimes), fm, max(ftimes)))
    print("  %-40s %.1f Hz mean, %.1f Hz worst"
          % ("which at 6 MHz is", 6000000 / fm, 6000000 / max(ftimes)))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
