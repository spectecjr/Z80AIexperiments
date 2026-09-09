#!/usr/bin/env python3
"""Verify and time democube.z80s.

Runs the Z80 frame update alongside a model of the same arithmetic and
compares the whole state every frame, then runs the model alone for a
million frames to check the thing it claims: that the cube stays in
the frustum and keeps its speed, forever.

    pip install z80
    python3 tests/test_democube.py [--long]
"""
import math
import sys

from bench import Bench
from test_transform3d import model as t3d_model, s8, s16

S, R = 40, 70
BX, BY, ZN, ZF = 160, 120, 80, 240      # the box, in world units
XLIM, YLIM = (BX - R) * 128, (BY - R) * 128     # inset by the sphere
ZMIN, ZMAX = (ZN + R) * 128, (ZF - R) * 128
SIN = [max(-127, min(127, round(127 * math.sin(2 * math.pi * i / 256))))
       for i in range(256)]
VERTS = [(x, y, z) for x in (S, -S) for y in (S, -S) for z in (S, -S)]


def asr(v, n):
    return v >> n                      # Python >> on ints is arithmetic


def smul7(a, b):
    neg = (a ^ b) & 0x80
    p = abs(a) * abs(b)
    r = ((p + 64) * 2) >> 8            # what the Z80 keeps: bits 14..7
    if r > 127:
        r = 127
    return -r if neg else r


def addsat(a, b):
    v = a + b
    return max(-127, min(127, v))


def rdiv(x, d):
    q = (abs(x) + d // 2) // d
    return -q if x < 0 else q


class Model:
    def __init__(self):
        self.a = [0, 0, 0]
        self.da = [3, 5, 2]
        self.p = [0, 0, 160 * 128]
        self.v = [700, 500, -400]
        self.f = [0, 0, 0]
        self.m = [0] * 9

    def spin(self):
        self.a = [(self.a[i] + self.da[i]) & 0xFF for i in range(3)]
        sa, ca = SIN[self.a[0]], SIN[(self.a[0] + 64) & 0xFF]
        sb, cb = SIN[self.a[1]], SIN[(self.a[1] + 64) & 0xFF]
        sc, cc = SIN[self.a[2]], SIN[(self.a[2] + 64) & 0xFF]
        sasb, casb = smul7(sa, sb), smul7(ca, sb)
        m = [0] * 9
        m[0] = smul7(cb, cc)
        m[3] = smul7(cb, sc)
        m[6] = 127 if -sb == 128 else -sb
        m[7] = smul7(sa, cb)
        m[8] = smul7(ca, cb)
        m[1] = addsat(smul7(sasb, cc), -smul7(ca, sc))
        m[2] = addsat(smul7(casb, cc), smul7(sa, sc))
        m[4] = addsat(smul7(sasb, sc), smul7(ca, cc))
        m[5] = addsat(smul7(casb, sc), -smul7(sa, cc))
        self.m = m

    def move(self):
        for i in range(3):
            acc = s16(self.v[i] + self.f[i])
            self.f[i] = acc & 15
            self.p[i] = s16(self.p[i] + asr(acc, 4))
        for i, lim in ((0, XLIM), (1, YLIM)):
            if self.p[i] >= lim and self.v[i] >= 0:
                self.v[i] = -self.v[i]
            elif self.p[i] < -lim and self.v[i] < 0:
                self.v[i] = -self.v[i]
        if self.p[2] >= ZMAX and self.v[2] >= 0:
            self.v[2] = -self.v[2]
        elif self.p[2] < ZMIN and self.v[2] < 0:
            self.v[2] = -self.v[2]

    def frame(self, recip=None):
        self.spin()
        self.move()
        if recip is None:
            return None
        return t3d_model(VERTS, self.m, self.p, recip)


def main():
    long_run = "--long" in sys.argv
    b = Bench("harness_demo.asm")
    s = s_syms = b.syms
    recip = list(b.peek(s["t3d_recip"], 256))
    b.call_regs(s["demo_init"])
    mod = Model()
    bad = 0
    frames = 3000
    times = []

    def state():
        g = lambda n, k=2: int.from_bytes(b.peek(s[n], k), "little", signed=(k == 2))
        return ([g("demo_ax", 1), g("demo_ay", 1), g("demo_az", 1)],
                [g("demo_px"), g("demo_py"), g("demo_pz")],
                [g("demo_vx"), g("demo_vy"), g("demo_vz")],
                [s8(x) for x in b.peek(s["t3d_m"], 9)])

    bounces = 0
    for frame in range(frames):
        v_before = list(mod.v)
        want = mod.frame(recip)
        t, _ = b.call_regs(s["demo_frame"])
        times.append(t)
        if mod.v != v_before:
            bounces += 1
        raw = b.peek(s["demo_screen"], 16)
        got = [(raw[i], raw[i + 1]) for i in range(0, 16, 2)]
        ga, gp, gv, gm = state()
        if (ga, gp, gv, gm) != (mod.a, mod.p, mod.v, mod.m) or got != want:
            bad += 1
            if bad <= 3:
                print("  MISMATCH frame %d" % frame)
                print("    angles %s / %s" % (ga, mod.a))
                print("    pos    %s / %s" % (gp, mod.p))
                print("    vel    %s / %s" % (gv, mod.v))
                print("    matrix %s / %s" % (gm, mod.m))
                print("    screen %s\n           %s" % (got[:4], want[:4]))
            if bad > 3:
                break
    print("  %-40s %6d frames, %d mismatches, %d bounces"
          % ("Z80 against the model, whole state", frames, bad, bounces))

    # --- does it actually bounce forever? -----------------------------
    n = 1000000 if long_run else 100000
    mod = Model()
    speed0 = sum(x * x for x in mod.v)
    worst = {"x": 1e9, "y": 1e9, "z": 1e9}
    smin = smax = speed0
    bounces = 0
    for _ in range(n):
        v_before = list(mod.v)
        mod.frame()
        if mod.v != v_before:
            bounces += 1
        px, py, pz = mod.p
        worst["x"] = min(worst["x"], XLIM - abs(px))
        worst["y"] = min(worst["y"], YLIM - abs(py))
        worst["z"] = min(worst["z"], ZMAX - pz, pz - ZMIN)
        sp = sum(x * x for x in mod.v)
        smin, smax = min(smin, sp), max(smax, sp)
    print("  %-40s %6d frames, %d bounces" % ("model long run", n, bounces))
    print("    deepest the centre gets past a wall, in 9.7 units:")
    print("      x %d, y %d, z %d   (one frame of travel is about %d)"
          % (worst["x"], worst["y"], worst["z"],
             max(abs(v) for v in mod.v) // 16))
    print("    speed stays within %.4f%% .. %.4f%% of where it started"
          % (100 * math.sqrt(smin / speed0), 100 * math.sqrt(smax / speed0)))
    if min(worst.values()) < -400:
        print("    *** it got out ***")
        bad += 1
    if not 0.99 < math.sqrt(smin / speed0) or not math.sqrt(smax / speed0) < 1.01:
        print("    *** the speed drifted ***")
        bad += 1

    print()
    print("  demo_frame   min %d T-states, mean %.0f, max %d"
          % (min(times), sum(times) / len(times), max(times)))
    print("  which is %.1f%% of a 69,888 T-state PAL frame, %.1f%% of 192,000"
          % (100 * (sum(times) / len(times)) / 69888,
             100 * (sum(times) / len(times)) / 192000))
    print("  where it goes:")
    parts = [("demo_spin   angles and the rotation matrix", "demo_spin"),
             ("demo_move   integrate and bounce", "demo_move"),
             ("demo_tables nine coefficients, two entries each", "demo_tables")]
    for label, sym in parts:
        ts = []
        for _ in range(200):
            b.call_regs(s_syms["demo_frame"]) if False else None
            ts.append(b.call_regs(s_syms[sym])[0])
        print("    %-46s %6d T" % (label, min(ts)))
    ts = []
    for _ in range(50):
        t, _ = b.call_regs(s_syms["t3d_run"], hl=s_syms["demo_verts"],
                           de=s_syms["demo_screen"], bc=8 << 8)
        ts.append(t)
    print("    %-46s %6d T" % ("t3d_run     project the eight corners",
                               min(ts)))

    print("\n%s" % ("ALL TESTS PASSED" if bad == 0 else "FAILURES: %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
