#!/usr/bin/env python3
"""Verify and time vox.z80s against tests/vox.py.

    pip install z80
    python3 tests/test_vox.py
"""
import math
import sys

from bench import Bench
import vox as V

BUF = {0x80: 0x8000, 0x20: 0x2000}


def main():
    b = Bench("harness_vox.asm", org=0)
    s = b.syms
    b.call_regs(s["vx_init"])
    mp = list(b.peek(s["vx_map"], 256))
    rt = list(b.peek(s["vx_row"], 256))
    ct = list(b.peek(s["vx_col"], 256))
    bad = 0
    times = []
    for k in range(16):
        ang = 2 * math.pi * k / 16
        px = (0x0800 + k * 271) & 0xFFFF
        py = (0x8000 + k * 907) & 0xFFFF
        dx0 = int(1.5 * 256 * math.cos(ang - 0.5)) & 0xFFFF
        dy0 = int(1.5 * 4096 * math.sin(ang - 0.5)) & 0xFFFF
        sx = int(1.5 * 256 * (math.cos(ang + 0.5)
                              - math.cos(ang - 0.5)) / 63) & 0xFFFF
        sy = int(1.5 * 4096 * (math.sin(ang + 0.5)
                               - math.sin(ang - 0.5)) / 63) & 0xFFFF
        for n, v in (("vx_px", px), ("vx_py", py), ("vx_dx0", dx0),
                     ("vx_dy0", dy0), ("vx_sx", sx), ("vx_sy", sy)):
            b.poke(s[n], v.to_bytes(2, "little"))
        into = b.peek(s["vx_back"], 1)[0]
        t, _ = b.call_regs(s["vx_frame"])
        times.append(t)
        dxs, dys = [], []
        for c in range(V.COLS):
            dxs.append((dx0 + c * sx) & 0xFFFF)
            dys.append((dy0 + c * sy) & 0xFFFF)
        want = V.frame(mp, rt, ct, px, py, dxs, dys)
        got = b.peek(BUF[into], V.STRIDE * V.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  MISMATCH %d: %d bytes, first at y=%d byte=%d "
                      "got %02X want %02X"
                      % (k, len(d), d[0] // V.STRIDE, d[0] % V.STRIDE,
                         got[d[0]], want[d[0]]))
    n = len(times)
    mean = sum(times) / n
    px_n = V.COLS * 2 * V.VH
    print("  %-40s %4d camera positions, %d mismatches"
          % ("Z80 against the model", n, bad))
    print()
    print("  vx_frame     min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %d samples, %d bytes drawn"
          % ("for", V.COLS * V.STEPS, px_n))
    print("  %-40s %.1f Hz" % ("which at 6 MHz is", 6e6 / mean))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
