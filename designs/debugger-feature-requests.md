# SimCoupe: debugger interface feature requests

Notes toward an external debugger/automation interface for SimCoupe, written
from one concrete use case: automated verification of generated Z80 code.

This is a wishlist, not a specification. It comes from building
[codesprite](../tools/codesprite/) — a compiler that turns sprites into
straight-line Z80 that draws itself on a SAM in mode 4 — and hitting two things
that no amount of work inside that project can settle. Everything here is
offered as input to someone else's design decisions; if a request is awkward to
implement, it is almost certainly not worth the trouble.

## Why an external interface would help

The sprite compiler is already checked fairly hard offline. Every routine it
emits is assembled to bytes, executed in a Z80 emulator written for the project,
and compared against a reference image drawn independently in Python — across
both pixel phases, both row parities and many screen positions. `pasmo`
assembles the same source and the bytes are compared, so the encodings are
confirmed by a third party. That is 344 tests and it catches a great deal.

Two gaps remain, and both are on the far side of a real emulator:

**1. The oracle is my own work.** Correctness is judged by an emulator I wrote,
against a model of the display I also wrote. A misunderstanding of the hardware
present in *both* passes every test silently. An independent implementation
running the same bytes and producing the same screen would settle it. This is a
one-off need — run the corpus once, compare, and the risk is retired — but there
is no way to do it today short of eyeballing a screenshot.

**2. Timing is nominal, and the SAM is not.** The optimiser chooses between
instruction sequences by cost, using textbook Z80 T-states. The real machine
stretches memory accesses via the ASIC, and mode 4 during the active display is
the worst case. The choices this actually decides are not academic:

| | nominal | bytes written | nominal per byte |
|---|---|---|---|
| `PUSH rr` | 11T | 2 | 5.5T |
| `LD (HL),n` | 10T | 1 | 10T |
| `LD (HL),r` | 7T | 1 | 7T |

The whole reason the generator goes to the trouble of pointing SP into the
display file is that first row. If contention flattens those ratios — or worse,
reorders them — then the "best" plan it picks is not the fastest one on
hardware, and it is optimising confidently in the wrong direction. I cannot tell
from here. Measuring one routine two ways would tell me immediately.

## The four primitives

Enough for a verification loop, in rough order of what they enable:

1. **Write a block of bytes to an address.** Inject a routine and a known screen
   without building a disk image. The single biggest saving in iteration time —
   it removes the whole disk round-trip from the loop.
2. **Set registers and PC, then run.** The generated routines take their
   arguments in registers (`HL` = screen address, `DE` = scratchpad), so being
   able to set those and jump is what makes a routine callable in isolation.
3. **Run deterministically and stop predictably** — until `HALT`, until a
   breakpoint, or for N instructions. Determinism matters more than the
   stopping condition: the same input must give the same result every run, or
   it cannot be a test.
4. **Read a memory range back.** Chiefly the 24K display file at `$8000`, to
   compare against the expected image.

And the one that produces information I cannot get any other way:

5. **Read the elapsed T-state count across a run.**

That last one is the most valuable single item on the list. Everything else
confirms something I already believe; the cycle count tells me something new,
and it is what would let the optimiser be calibrated against the real machine
instead of a textbook.

One question it depends on, which you will know and I do not: **does SimCoupe's
cycle counter reflect ASIC contention, or is it nominal Z80 timing?** If it is
nominal, item 5 is worth much less — it would confirm my model rather than
correct it — and I would not want it prioritised on my account.

## The loop this makes possible

```
  write   $8000..$DFFF  <- a known test image
  write   $4000         <- the routine under test
  set     HL = $8000+addr, DE = scratch, PC = $4000
  run     until HALT
  read    $8000..$DFFF  -> compare against the expected image
  read    T-states      -> compare against the cost model
```

Roughly ten of those per sprite, over a corpus of a few dozen. Nothing
performance-sensitive: if each round trip took a second it would still be far
quicker than the alternative, which is not doing it.

## Transport

Deliberately undemanding. A line-based text protocol over a TCP socket is
trivial to implement on your side and trivial to drive from Python on mine —
something as plain as:

```
> poke 4000 3E,10,32,00,80,76
< ok
> setreg hl=8000 de=6000 pc=4000
< ok
> run halt
< stopped pc=4006 tstates=1094
> peek 8000 100
< 10,00,00,...
```

A command file replayed at startup would work nearly as well and needs no socket
handling at all, at the cost of not being able to react to what came back.

The obvious alternative is the **GDB remote serial protocol**, which brings
existing tooling for free. I would gently steer away from it: Z80 support in GDB
is patchy, the protocol carries a lot of weight this use case does not need, and
a bespoke text protocol is probably less work for both of us. Worth naming only
so the option is on the table.

## Nice to have, ranked below the above

* **Headless / batch mode with a meaningful exit code**, so this can run in CI
  rather than only on a desk.
* **Screen dump straight to PNG.** I can reconstruct an image from a memory
  range, but a native dump would make failures human-readable instantly, which
  matters more than it sounds when a test says "3 bytes differ".
* **Breakpoint by address**, for stopping somewhere other than a `HALT` — useful
  for measuring a section of a routine rather than the whole thing.
* **Load a snapshot at startup**, so a session begins from a known state without
  booting a disk each time. Mostly a speed and determinism convenience.

## What it unblocks here

With the memory primitives, the sprite corpus gets checked against an
independent implementation of the hardware, and the emulator underneath the
whole toolchain stops being taken on trust.

With the cycle counter, the optimiser's objective can move from nominal
T-states to measured ones. That is the difference between a compiler that
produces provably correct code at a plausible speed, and one that produces the
fastest code the machine will actually run.

Neither is blocking. The offline path works and the project continues without
any of this. But the second one in particular changes what the tool can honestly
claim.
