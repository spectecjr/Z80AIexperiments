#!/usr/bin/env python3
"""Verify and time scroll8.z80s - the whole display up by eight lines.

    python3 tests/test_scroll8.py

Three things are checked, and the last two are the point of the file:

  1. the picture, byte for byte against tests/scroll8.py;
  2. how long interrupts are disabled for, measured by single-stepping
     the routine and timing every stretch between two boundaries at
     which an interrupt could be accepted - the brief is 400 T-states;
  3. that an interrupt taken at any of those boundaries is harmless,
     by writing junk below SP at every one of them and checking the
     picture still comes out exact.
"""
import sys

from bench import Bench, FRAME, RETADDR
import scroll8 as S

STACK = 0xFEFE          # what the bench calls the routine with
SAFE = 64               # bytes below SP an interrupt handler may use


def run(b, entry, screen, stack=STACK):
    """Call the routine over a screen; returns (picture, T-states, SP)."""
    b.poke(S.SCR, screen)
    m = b.m
    b.poke(stack, bytes([RETADDR & 0xFF, RETADDR >> 8]))
    m.sp = stack
    m.iff1 = m.iff2 = True          # a caller with the interrupt on
    m.pc = entry
    m.halted = False
    total = 0
    prev = m.frame_tick
    for _ in range(400):
        m.ticks_to_stop = FRAME // 2
        m.run()
        step = m.frame_tick - prev
        total += step + FRAME if step < 0 else step
        prev = m.frame_tick
        if m.pc == RETADDR:
            break
    else:
        raise RuntimeError("routine did not return (runaway loop?)")
    return b.peek(S.SCR, S.SIZE), total, m.sp


def elsewhere(b):
    """Everything outside the screen, so a stray push can be spotted."""
    return b.peek(0, S.SCR) + b.peek(S.SCR + S.SIZE, 0x10000 - S.SCR - S.SIZE)


def walk(b, entry, screen, hostile=False):
    """Single-step the routine, watching the interrupt.

    Returns (T-states, the longest stretch with the interrupt shut out,
    how many times SP was somewhere an interrupt could not safely push).
    With hostile=True, every boundary where an interrupt could be taken
    gets one written below SP, which is what an accepted interrupt does
    to memory.
    """
    m = b.m
    b.poke(S.SCR, screen)
    m.sp = STACK
    m.iff1 = m.iff2 = True          # a caller with the interrupt on
    m.pc = entry
    m.halted = False
    total = span = worst = 0
    unsafe = 0
    while m.pc != RETADDR:
        if m.iff1 and not m.int_disabled:        # an interrupt lands here
            worst = max(worst, span)
            span = 0
            lo = (m.sp - SAFE) & 0xFFFF
            if not (lo >= S.SCR + S.SIZE or m.sp <= S.SCR):
                unsafe += 1
            if hostile:
                b.poke((m.sp - 2) & 0xFFFF, b"\xC7\xC7")
        before = m.frame_tick
        m.ticks_to_stop = 1
        m.run()
        step = m.frame_tick - before
        step += FRAME if step < 0 else 0
        total += step
        span += step
        if total > 2000000:
            raise RuntimeError("routine did not return (runaway loop?)")
    return total, max(worst, span), unsafe


def main():
    b = Bench("harness_scroll.asm", org=0)
    s = b.syms
    bad = 0
    mean = {}
    screens = [S.pattern(seed) for seed in (0xACE1, 0x1234, 0xFFFF)]

    print("  %-12s %10s %8s %10s   %s"
          % ("", "T-states", "T a byte", "of 50 Hz", "the picture"))
    for name, entry, model in (("sc_scroll", "sc_scroll", S.scroll),
                               ("sc_scrolli", "sc_scrolli", S.scroll),
                               ("sc_clear", "sc_clear", S.clear),
                               ("sc_cleari", "sc_cleari", S.clear)):
        ts = []
        for scr in screens:
            got, t, sp = run(b, s[entry], scr)
            want = model(scr)
            ts.append(t)
            if got != bytes(want):
                bad += 1
                d = [i for i in range(S.SIZE) if got[i] != want[i]]
                print("  MISMATCH %s: %d bytes, first at %d (line %d, byte %d)"
                      % (name, len(d), d[0], d[0] // S.BPL, d[0] % S.BPL))
            if sp != STACK + 2:
                bad += 1
                print("  %s left SP at %04X, not %04X" % (name, sp, STACK + 2))
        moved = S.SIZE if model is S.scroll else S.SHIFT
        mean[name] = sum(ts) / len(ts)
        print("  %-12s %10d %8.2f %9.0f%%   %s"
              % (name, mean[name], mean[name] / moved,
                 100 * mean[name] / 120000,
                 "exact" if len(ts) and not bad else "SEE ABOVE"))

    print("  %-12s %10d %8.2f %9s   %s"
          % ("  the move", mean["sc_scroll"] - mean["sc_clear"],
             (mean["sc_scroll"] - mean["sc_clear"]) / S.MOVE, "",
             "23,552 bytes through the stack"))
    print("  %-12s %10d %8.2f %9s   %s"
          % ("  by LDI", mean["sc_scrolli"] - mean["sc_clear"],
             (mean["sc_scrolli"] - mean["sc_clear"]) / S.MOVE, "",
             "the same bytes, LDI unrolled 64"))

    print()
    print("  %-12s %10s %8s %9s   %s"
          % ("", "T-states", "worst DI", "in us", "an interrupt at every boundary"))
    for name in ("sc_scroll", "sc_scrolli", "sc_clear", "sc_cleari"):
        t, worst, unsafe = walk(b, s[name], screens[0])
        got, _, _ = run(b, s[name], screens[0])          # reset the screen
        th, _, _ = walk(b, s[name], screens[0], hostile=True)
        got = b.peek(S.SCR, S.SIZE)
        want = S.clear(screens[0]) if name.startswith("sc_clear") \
            else S.scroll(screens[0])
        ok = got == bytes(want)
        if not ok or unsafe or worst > 400:
            bad += 1
        print("  %-12s %10d %8d %9.1f   %s"
              % (name, t, worst, worst / 6.0,
                 "survives" if ok else "CORRUPTED"))
        if unsafe:
            print("      SP was inside the screen at %d enabled boundaries"
                  % unsafe)
        if worst > 400:
            print("      OVER BUDGET: %d T-states with the interrupt shut out"
                  % worst)

    # what the 400 T-state brief costs, measured by building the same
    # routine with twice as many blocks in a window (which is over the
    # brief, and is here for this line and nothing else)
    b4 = Bench("harness_scroll4.asm", org=0)
    got, t4, _ = run(b4, b4.syms["sc_scroll"], screens[0])
    if got != bytes(S.scroll(screens[0])):
        bad += 1
        print("  the four-block build does not match the model")
    m4 = t4 - mean["sc_clear"]
    m2 = mean["sc_scroll"] - mean["sc_clear"]
    w2 = S.MOVE // (8 * 2)
    w4 = S.MOVE // (8 * 4)
    per = (m2 - m4) / (w2 - w4)
    free = m2 - w2 * per
    print()
    print("  %-46s %.1f T-states" % ("a DI window, off the two builds", per))
    print("  %-46s %.0f" % ("the move with no windows at all", free))
    print("  %-46s %.1f%%" % ("which is what the 400 T-state brief costs",
                              100 * (m2 - free) / free))

    # the interrupt is on when it returns, nothing outside the screen was
    # touched, and the caller's stack is wherever the caller left it
    for name in ("sc_scroll", "sc_scrolli", "sc_clear", "sc_cleari"):
        b.poke(S.SCR, screens[0])
        before = elsewhere(b)
        _, _, sp = run(b, s[name], screens[0], stack=0x7F00)
        after = elsewhere(b)
        d = [i for i in range(len(before)) if before[i] != after[i]]
        d = [i for i in d if not (0x7EF0 <= i < 0x7F02)]     # the return address
        d = [i for i in d if not (s["sc_sp"] <= i < s["sc_sp"] + 2)]
        if d or sp != 0x7F02 or not b.m.iff1:
            bad += 1
            print("  %s: %d bytes outside the screen changed, SP %04X, IFF1 %s"
                  % (name, len(d), sp, b.m.iff1))

    print()
    print("  %-46s %d" % ("checks that failed", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
