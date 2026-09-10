# scroll8.z80s — design notes

The whole MODE 4 display up by eight scanlines, black underneath, with
the interrupt shut out for **53.7 µs at a time** and never longer.

Verified byte for byte against `tests/scroll8.py` over three screens of
LFSR noise, and — the part that matters here — verified with **an
interrupt's push written below SP at every boundary an interrupt could
be accepted at**, which leaves the picture exact.

## Interface

| symbol | |
|---|---|
| `sc_scroll` | the move and the clear, both through the stack |
| `sc_scrolli` | the same picture, the move done by `LDI` — **faster, and no interrupt latency in the move at all** |
| `sc_clear` | the bottom eight lines only, through the stack |
| `sc_cleari` | the same lines with `LD (HL),A`, for the comparison |
| `SC_SCR` | the display file, page aligned; 0x8000 |
| `SC_LINES` | scanlines to scroll by; 8 |

All four return with SP as they found it and **with interrupts
enabled** — a caller that had them off gets them back on.

## What the job actually is

24,576 bytes of screen, scrolled up eight lines: 23,552 bytes moved
1,024 down, and 1,024 bytes of black. Even at the floor — `POP` reads
two bytes in 10 T-states and `PUSH` writes two in 11, so 10.5 a byte —
and with SP moving between the two regions for nothing, the move alone
is **247,296 T-states, two 50 Hz frames**. There is no way to write
this that fits in a frame, which is the whole reason the interrupt has
to be let in while it runs.

## The block, and why it does not pay

A block is popped out of the source into every register that will hold
one and pushed back 1,024 bytes lower:

    LD SP,src    POP BC / POP DE / POP HL / POP IX
    LD SP,dst    PUSH IX / PUSH HL / PUSH DE / PUSH BC

Eight bytes for 92 T-states — **11.5 a byte, against `LDI`'s 16**. But
there are only eight bytes of register to amortise the two `LD SP`s
over, and getting SP from one region to the other and back is not one
instruction. The two pointers live in the alternate set, where `EXX`
reaches them without disturbing the block in flight:

    EXX / LD SP,HL / ADD HL,BC / EX DE,HL / EXX      29 T-states

twice a block. **58 T-states of the block's 150 — 39% of it — is
moving the stack pointer**, and that is the whole story: 18.75 T-states
a byte by the instruction timings — measured over the whole move, 18.86
with the interrupt left alone and 20.24 with the windows in — where
`LDI` measures 16.16 and is flat.

## Direction: the one thing that is not a choice

The picture moves *down* in memory, so the copy has to run *up* it. A
block written before its own contents were read would carry off the
source of a block 1,024 bytes further on — which is exactly the bug
this file was written with, and it corrupts 22,440 of 24,576 bytes in a
way that still looks like a picture.

That settles something that would otherwise be free money. `POP` walks
up and `PUSH` walks down, so whichever way round the blocks go, **one
of the two pointers lands exactly where the next block wants it and the
other does not**. Going up, it is the source: after the four pops SP is
already at the next block's source. It cannot be cashed in, because
pointing SP at the destination is precisely what destroys it, and
saving it across the pushes is `LD (nn),SP` and `LD SP,(nn)` — 40
T-states against the 29 that keeping the pointer in the alternate set
costs. So both pointers are kept and the free one is thrown away.

**The clear does cash it in.** Nothing there reads memory, so SP walks
down through the eight lines by itself and only the window boundaries
cost anything: 7.33 T-states a byte against `PUSH`'s floor of 5.5, and
the difference is entirely the interrupt.

## The interrupt window

While a block is in flight SP is inside the screen, so an interrupt
taken there pushes a return address into the picture — and on a SAM,
into whatever the line interrupt was about to do. So the run is `DI`,
cut into windows of two blocks:

    DI / <two blocks> / LD SP,IY / EI / NOP / DI ...

`EI` does not take effect until after the instruction that follows it,
so **the `NOP` is not padding — it is the only boundary at which the
interrupt can be accepted**. `EI / DI` would let nothing in at all.

What SP is put back to is the caller's own stack, kept in `IY`:
`LD SP,IY` is 10 T-states where `LD SP,(nn)` is 20, and `IY` is the one
register pair the move has no other use for. The clear uses `IX` for
it, `IY` being its screen pointer by then.

Eight windows are unrolled between loop tests, so the test is 14
T-states over 128 bytes rather than over 16, and the group count fits
in `A` — which survives `EXX`, and which the blocks never touch.

## What it costs

Every figure measured by `tests/test_scroll8.py`.

| | T-states | a byte | worst DI |
|---|---|---|---|
| **`sc_scroll`** | **484,155** | 19.70 | **322 — 53.7 µs** |
| **`sc_scrolli`** | **388,062** | 15.79 | 232 — 38.7 µs |
| the move, through the stack | 476,645 | 20.24 | 322 |
| the move, `LDI` unrolled 64 | 380,552 | 16.16 | **never disabled** |
| the clear, through the stack | 7,510 | **7.33** | 232 |
| the clear, `LD (HL),A` / `INC HL` | 13,567 | 13.25 | never disabled |

A byte column is over the 24,576 the whole screen holds for the two
scrolls, and over the bytes actually written for the halves.

**What the 400 T-state brief costs**, measured by building the same
routine twice, with two blocks in a window and with four:

| | |
|---|---|
| a DI window | **22.0 T-states** |
| the move with no windows at all | 444,261 — 18.86 a byte |
| so the brief costs | **7.3%** |

That is the honest price of the requirement, and it is cheap. The
expensive part is the technique.

## The verdict

**The stack loses the move and wins the clear.**

- moving 23,552 bytes: 476,645 through the stack against 380,552 by
  `LDI` — the stack is **25% slower**, and it is the one that has to
  turn the interrupt off. `LDI` never touches SP, so `sc_scrolli`'s
  move has no interrupt latency to argue about at all.
- clearing 1,024: 7,510 through the stack against 13,567 — the stack
  is **45% cheaper**, windows and all.

Which is the general shape of it, and matches everything else measured
in this repo (`tricks.md` §1): a `PUSH` fill is unbeatable at 5.5
T-states a byte because the source is a register, and a `PUSH` *copy*
is not, because every eight bytes of copy has to move the stack pointer
twice and there are only eight bytes of register to pay for it.

**Use `sc_scrolli`.** `sc_scroll` is here because the question was
asked, and because the measurement is worth having written down.

## Invariants

- **The interrupt handler must preserve what it uses** — including the
  alternate set, `IX`, `IY` and `A`, which is where this routine's
  whole state lives across a window. A handler that uses `EXX` without
  putting it back will take the screen with it — check yours before
  using this.
- Blocks run upwards, source first. Reversing them corrupts the picture
  (above).
- Pushes must be the exact reverse of the pops, or every block comes
  out with its four pairs in the wrong order.
- `SC_SCR` is page aligned and `SC_MOVE` divides exactly by the block,
  the window and the group. All of it is `ASSERT`ed at assembly time,
  because the loop has no end test in it, only a count.
- The routine writes two bytes of its own (`sc_sp`) and nothing else
  outside the screen; the test checks that too.

## If you pick this up

1. **Ten-byte blocks.** Adding `IY` to the block makes it 179 T-states
   for ten bytes — 17.9 a byte against 18.75, both by instruction
   count — but 23,552 is
   1,024 × 23, so only a power-of-two block divides it, and a ten-byte
   block needs a twelve-byte tail. About 8% of the move, for a special
   case. The window would be 380 T-states, which is still inside the
   brief but not by much.
2. **Make it resumable.** The window structure already cuts the work
   into 1,472 pieces with nothing live in registers between them except
   the two pointers. Spilling those to memory at a window boundary and
   returning turns this into "scroll for as long as I have left this
   frame" — which is what a scrolling demo actually wants, given that
   the job is four frames long however it is written.
3. **Scroll less.** Nothing above needs the whole screen: a viewport of
   96 lines is half the cost, and a viewport whose bottom eight lines
   are the only ones that change is a different routine altogether.
4. **There is no hardware answer on a SAM.** `VMPR` moves the display
   file in 16K steps, so eight lines of 128 bytes cannot be had by
   changing where the screen is.

    python3 tests/test_scroll8.py    # verify, time, and check the latency
