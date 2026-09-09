#!/usr/bin/env python3
"""Verify and time room3d.z80s against a model of the same renderer.

Walks a camera round the room and compares every drawn byte with
room.py, then reports what a frame costs against the 240,000 T-states
a 6 MHz SAM has between 25 Hz frames.

    pip install z80
    python3 tests/test_room3d.py
"""
import sys

from bench import Bench
import room

BUF = {0x80: 0x8000, 0x20: 0x2000}
PAL = ([(0, 0, 0)]                                       # 0  letterbox
       + [(28 + 32 * i, 12 + 13 * i, 9 + 8 * i) for i in range(6)]     # 1-6
       + [(72, 60, 44)]                                  # 7  floor
       + [(10 + 11 * i, 15 + 15 * i, 32 + 32 * i) for i in range(6)]   # 8-13
       + [(24, 24, 42)]                                  # 14 ceiling
       + [(255, 255, 255)])


def s16(v):
    return v - 0x10000 if v > 0x7FFF else v


def path(t):
    """A camera walk: a lap of the room while turning."""
    import math
    return (int(70 * math.sin(2 * math.pi * t / 128)),
            int(55 * math.cos(2 * math.pi * t / 96)),
            (t * 3) & 255)


def main():
    b = Bench("harness_room.asm", org=0)
    s = b.syms
    nw = b.peek(s["r3d_nw"], 1)[0]
    raw = b.peek(s["r3d_rx"], 4 * nw)
    verts = [(s16(raw[4 * i] | raw[4 * i + 1] << 8),
              s16(raw[4 * i + 2] | raw[4 * i + 3] << 8)) for i in range(nw)]
    colours = list(b.peek(s["r3d_rc"], nw))
    ceil_col = b.peek(s["r3d_scc"], 1)[0] & 15
    floor_col = b.peek(s["r3d_sfc"], 1)[0] & 15
    print("  room %s, ramps %s" % (verts, colours))

    b.call_regs(s["r3d_init"])
    bad = 0
    times = []
    strips = []
    frames = 256
    shown = None
    for f in range(frames):
        cx, cz, ca = path(f)
        b.poke(s["r3d_cx"], (cx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_cz"], (cz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_ca"], bytes([ca]))
        drawn_into = b.peek(s["r3d_back"], 1)[0]
        t, _ = b.call_regs(s["r3d_frame"])
        times.append(t)
        want, st = room.render(verts, colours, (cx, cz, ca),
                               ceil_col, floor_col)
        strips.append(len(st))
        got = b.peek(BUF[drawn_into], room.STRIDE * room.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                diff = [i for i in range(len(want)) if got[i] != want[i]]
                print("  MISMATCH frame %d cam %s: %d bytes differ, first at "
                      "%d (y=%d x=%d) got %02X want %02X"
                      % (f, (cx, cz, ca), len(diff), diff[0],
                         diff[0] // room.STRIDE, (diff[0] % room.STRIDE) * 2,
                         got[diff[0]], want[diff[0]]))
                print("     strips %s" % (st,))
        elif shown is None and len(st) == 3:
            shown = got
    print("  %-40s %6d frames, %d mismatches"
          % ("Z80 buffer against the model", frames, bad))
    print("  %-40s min %d, mean %.2f, max %d"
          % ("walls drawn a frame", min(strips),
             sum(strips) / len(strips), max(strips)))
    print()
    print("  r3d_frame    min %d T-states, mean %.0f, max %d"
          % (min(times), sum(times) / len(times), max(times)))
    print("  %-40s %.0f%% of 240,000 (25 Hz on a 6 MHz SAM)"
          % ("mean", 100 * (sum(times) / len(times)) / 240000))
    print("  %-40s %.0f%% of 120,000 (50 Hz)"
          % ("mean", 100 * (sum(times) / len(times)) / 120000))
    if shown is not None:
        room_png(shown, "/tmp/z80room.png")
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


def room_png(buf, path_):
    import raster
    raster.to_png(buf, path_, PAL)


if __name__ == "__main__":
    sys.exit(main())
