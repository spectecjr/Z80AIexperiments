#!/usr/bin/env python3
"""Build and check contend.z80s - the contention test that runs on iron.

    python3 tests/mkcontend.py

`contend.z80s` measures the SAM's memory contention with nothing but the
machine: wait for the frame interrupt, run a known number of
instructions, read the light pen's line register. Where the raster got to
is the elapsed time, at 384 T-states a line.

This assembles it, runs it here under the contention model `costs.md`
budgets against - SimCoupe's rules, applied through `tests/sam.py` - and
prints what that model says each test will read, beside what two rival
models say. Then it writes **`build/contend.sbt`**, which SimCoupe boots straight into:
its `FileDisk` wraps a raw file as a bootable disk with the CODE type, a
start of 0x8000, first page 1 and auto-execute set - which is exactly the
SAM's own entry convention. Insert it, or pass it on the command line, and
it runs.

**The answers disagree loudly**, which is the point: a `PUSH` under no
contention, under one-access-a-slot, and under every-access-aligned ends
on three very different display lines. Whatever SimCoupe or a real SAM
prints into RESULT settles which of them this repository should believe.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import z80                                              # noqa: E402
from bench import MEMOFF                                # noqa: E402
from sam import Sam                                     # noqa: E402

T_LINE, TOP, FRAME_T = 384, 68, 119808
RESULT, ENTRY = 0xFF00, 0x8000
TESTS = ("PUSH DE", "NOP", "LD (HL),A")

# WHAT THE MACHINE SAID. Run under SimCoupe, which is cycle accurate:
# booted from this very .sbt, through SAMDOS, with a real raster and real
# interrupts, and the three answers read out of B, C and D.
#
# They are the model's, exactly. That is the oracle now: if a change to
# the contention model in tests/sam.py moves any of these, the model has
# drifted away from the machine and this fails.
MEASURED = {"PUSH DE": 132, "NOP": 26, "LD (HL),A": 90}


def build():
    out = os.path.join(ROOT, "build")
    os.makedirs(out, exist_ok=True)
    binf = os.path.join(out, "contend.sbt")
    r = subprocess.run(["sjasmplus", "--raw=" + binf,
                        os.path.join(ROOT, "contend.z80s")],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stdout + r.stderr)
    return binf, open(binf, "rb").read()


def run(image, contend=True):
    """The program, with the SAM's wait states counted into the clock.

    The machine here is flat 64K, which is what the program needs: it
    pages nothing, and on a real SAM sections C and D hold pages 1 and 2
    where it was loaded.
    """
    m = z80.Z80Machine()
    m.set_memory_block(ENTRY, image)
    st = {"t": 0, "prev": 0}
    view = m.get_state_view()

    def clock():
        step = m.frame_tick - st["prev"]
        if step < 0:
            step += 100000                      # the module's own wrap
        st["prev"] = m.frame_tick
        st["t"] += step
        return st["t"]

    def wait(t):
        return Sam._mem_wait(t) if contend else 0

    # NB: two statements, not `st["t"] += wait(clock())`. An augmented
    # assignment loads the target before evaluating the right hand side,
    # so a clock() that updates st["t"] inside it would be overwritten.
    def rd(addr):
        w = wait(clock())
        st["t"] += w
        return view[MEMOFF + addr]

    def wr(addr, value):
        w = wait(clock())
        st["t"] += w
        view[MEMOFF + addr] = value
        return 0

    def inp(addr):
        t = clock()
        if contend:
            w = 7 - (t & 7)                     # an ASIC port, always
            st["t"] += w
            t = st["t"]
        port, hi = addr & 0xFF, addr >> 8
        if port == 249:                         # STATUS: bit 3 low for the
            within = (t % FRAME_T) < 128        # first 128 T of a frame
            return 0xFF & ~8 if within else 0xFF
        if port == 0xF8 and hi == 0x01:         # HPEN: the display line
            line = (t % FRAME_T) // T_LINE - TOP
            return line if 0 <= line < 192 else 192
        return 0xFF

    def out(addr, value):
        if contend and (addr & 0xFF) >= 0xF8:
            w = 7 - (clock() & 7)
            st["t"] += w

    marks = z80.Z80Machine.READ_MARK | z80.Z80Machine.WRITE_MARK
    m.set_read_callback(rd)
    m.set_write_callback(wr)
    m.set_input_callback(inp)
    m.set_output_callback(out)
    m.mark_addrs(0, 0x10000, marks)
    m.pc, m.sp, m.halted = ENTRY, 0x7FF0, False
    for _ in range(4000):
        m.ticks_to_stop = 50000
        m.run()
        if m.halted:
            break
    else:
        raise SystemExit("contend.z80s did not halt")
    return [view[MEMOFF + RESULT + i] for i in range(3)], st["t"]


def main():
    binf, image = build()
    print("  %-28s %d bytes, entered at 0x%04X"
          % ("build/contend.sbt", len(image), ENTRY))

    free, _ = run(image, contend=False)
    held, t = run(image, contend=True)
    print()
    print("  the display line each test ends on")
    print("  %-14s %13s %10s %10s" % ("", "no contention", "the model",
                                      "SimCoupe"))
    bad = []
    for i, name in enumerate(TESTS):
        want = MEASURED[name]
        flag = "" if held[i] == want else "   <-- DRIFTED"
        if held[i] != want:
            bad.append(name)
        print("  %-14s %13d %10d %10d%s" % (name, free[i], held[i], want,
                                            flag))
    print()
    print("  %-14s a slot division would put PUSH DE at 101 and no"
          % "")
    print("  %-14s contention at all at 49. The machine says %d."
          % ("", MEASURED["PUSH DE"]))
    print()
    print()
    print("  to run it:  simcoupe build/contend.sbt     (or insert the disk)")
    print("  %-14s it boots itself, runs for about three frames and halts;"
          % "")
    print("  %-14s then read three bytes at 0x%04X in the debugger."
          % ("", RESULT))

    print("\n%s" % ("ALL TESTS PASSED" if not bad
                    else "FAILURES: the model disagrees with the machine "
                         "about " + ", ".join(bad)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
