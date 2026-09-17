---
name: sam-coupe-hardware
description: The SAM Coupé's ports, memory paging and screen modes, as the demos in this repo need them - LMPR/HMPR/VMPR paging and what it means for a memory map, the CLUT and its port-addressing trap, the line interrupt, the border, and contention. Use when writing or changing a routine that pages memory, double buffers, flips the palette, or budgets a frame.
---

# The SAM Coupé, for this repo

Source: the SAM Coupé Technical Manual
(github.com/stefandrissen/sam-coupe-technical-manual). Anything below that
the manual does not state outright is marked *inferred*.

## The machine

- Z80B at 6 MHz. **120,000 T-states between 50 Hz interrupts, 240,000 at
  25 Hz** - `costs.md` budgets against these.
- 256K fitted as standard, 512K with the internal expansion, addressed as
  **32 pages of 16K**. The lower 5 bits of a paging register pick the page,
  so a 256K machine uses pages 0-15.
- The Z80's 64K is four 16K **sections**: A `0000`, B `4000`, C `8000`,
  D `C000`. A+B is the **low block**, C+D the **high block**.

## Paging - LMPR (250) and HMPR (251)

**LMPR** pages the low block, **HMPR** the high block, and the rule that
shapes every memory map is:

> the second section of a block is *always* the page above the first.

`LMPR = 4` puts page 4 at `0000` and page 5 at `4000`. You cannot choose the
two halves independently, so there is no way to hold one half still while
paging the other.

| | LMPR (250) | HMPR (251) |
|---|---|---|
| bits 0-4 | page for section A (B gets page+1) | page for section C (D gets page+1) |
| bit 5 | **RAM0** - set to put RAM over ROM 0 in section A | MD3S0 - CLUT address bit, MODE 3 only |
| bit 6 | **ROM1** - set to put ROM 1 over RAM in section D | MD3S1 - CLUT address bit, MODE 3 only |
| bit 7 | **WPRAM** - set to write-protect section A | MCNTRL - set to address *external* memory in C and D |

A demo that wants plain RAM everywhere writes `page | 0x20` to LMPR (RAM0
set, ROM1 and WPRAM clear) and `page` to HMPR.

Both registers are readable, so a routine can save and restore the caller's
paging rather than assuming it.

## The screen - VMPR (252)

- bits 0-4: the page the **video hardware** displays. bits 5-6: MDE0/MDE1,
  the screen mode. bit 7 is MIDI, not video.
- *Inferred*: the mode bits are `mode - 1`, so MODE 4 is `0x60 | page`. The
  manual gives MDE0/MDE1 only as "first/second bit of screen mode control",
  but the ROM's `JMODE` takes 0-3 for MODEs 1-4.
- **MODE 4**: 256x192, 16 colours from 128, 4 bits a pixel, high nibble is
  the *left* pixel of the two, 128 bytes a line, **24,576 bytes** a screen.
  MODE 3 is 512x192 in 4 colours over the same 24K.
- A 24K screen crosses a page boundary, so **the video page must be even**:
  the hardware wraps from the even page into the odd one above it, always
  within the same pair.
- A screen therefore leaves **8K spare** at the end of its odd page. The ROM
  uses it as scratch (`JGRAB`, `JFILL`); a demo can put code or tables there.

**The displayed page does not have to be mapped into the CPU's address
space.** VMPR points the display hardware straight at RAM. Double buffering
costs 24K of address space, not 48K: map the back buffer, draw, then flip
with one `OUT` to VMPR and one to HMPR.

## Laying out a demo that pages

Two registers, and the pair rule, mean that **if you page a data bank *and*
double buffer, nothing in the address space is permanently mapped**. The way
out is to duplicate, and to know what may be duplicated:

- **Read-only code and tables**: duplicate freely - put the routine in the
  spare 8K after *each* screen, so it stays mapped while the bank pages
  underneath it. Self-modified immediates are safe if every frame patches
  them before drawing.
- **Per-buffer state is duplicated *correctly***. A double-buffered routine
  that records what it last painted into each buffer wants exactly one copy
  of that record per buffer, which is what the spare 8K gives it for free.
- **Anything genuinely global** (a frame counter, the camera) has to be
  written by the caller into whichever copy is mapped, or derived from the
  hardware - `IN A,(252)` says which buffer is displayed, so the routine need
  not store it.
- Page the bank with **LMPR** and the screens with **HMPR**: then a bank
  switch mid-frame cannot pull the code out from under itself, because the
  code is in the high block with the screen.

A bank switch is `OUT (250),A` - **11 T-states**. If the rows of a picture
are drawn in an order that walks the bank monotonically, a bank of any size
costs a handful of those a frame.

**The stack is in a page too, and this is the trap.** A `CALL` writes the
return address to whatever is mapped now; the `RET` reads it from whatever
is mapped then. So, for any routine that pages the low block while the
caller's stack is in it:

- put the caller's page back **before returning**;
- **never `CALL` across a switch** - inline the switch, or jump to it;
- a routine that also puts `SP` on the screen must put `SP` back before
  anything in it calls anything.

Nothing complains when this is wrong: the `RET` goes to whatever those two
bytes happen to be in the page that is there now.

**Count the pages before committing to a map.** A 256K machine has sixteen
and they go quickly: a compiled run bank and its lookup tables can be ten of
them on their own, two buffers are four, and a compiled sprite is one more.
`chequer8` needs twenty, which is a 512K machine - worth deciding on
purpose rather than discovering.

## The palette - CLUT (base 248)

Sixteen write-only 7-bit registers, **one port each**: colour *n* is at port
`n * 256 + 248` (248, 504, 760 ... 4088).

    bit 0 BLU0   bit 1 RED0   bit 2 GRN0   bit 3 BRIGHT
    bit 4 BLU1   bit 5 RED1   bit 6 GRN1

so each channel is two bits plus a shared half-intensity bit: 128 colours.
`tests/mkchqdata.py`'s `sam(r, g, b)` builds one of these from 0-6 levels.

**The trap**: `OUT (n),A` puts **A** on the high address byte, which for the
CLUT *is* the register select. `OUT (248),A` therefore writes colour A, not
colour 0. Use `LD BC,n*256+248 : OUT (C),A`, or the manual's trick:

    LD   HL,table+16
    LD   B,16
    LD   C,248
    OTDR            ; B is both the count and the register select

LMPR, HMPR and VMPR decode on the low byte alone, so `OUT (250),A` is fine
for those.

## Interrupts and the border

- **LINE INT (249, write)**: interrupt at the end of the scanline *before*
  the one written, 0-191; write 192-255 to disable. This is the only
  mid-screen palette or mode change, and it is always enabled.
  `road2.md` measures what it costs: ~150 T-states a line with entry and
  exit, **28,800 a frame over 192 lines**, and it cannot fire at all during
  a `PUSH` fill, because the fill holds `SP` on the screen and an interrupt
  would push `PC` into the picture.
- **STATUS (249, read)**: bit 0 line, bit 1 mouse, bit 2 MIDI in, **bit 3
  frame**, bit 4 MIDI out - each *low* when requesting. Bits 5-7 are
  keyboard matrix lines 6-8. All five interrupts share IM 1, so the handler
  has to read this to know which fired.
- **BORDER (254, write)**: bits 0-2 and 5 are the CLUT address for the
  border colour, bit 3 MIC, bit 4 BEEP, bit 6 THROM (MIDI through),
  **bit 7 SOFF** - blanks the display in MODEs 3 and 4 *and removes memory
  contention while it is off*, which is worth having during a precompute.
- **KEYBOARD (254, read)**: bits 0-4 are matrix lines 1-5 (and the mouse),
  bit 7 reads back SOFF.

## Contention

Contention is **consistent in internal memory whatever the paging set-up**,
so a routine's T-state count does not change because it pages. The repo's
figures are raw Z80 T-states with real contention on top - `costs.md` says
so at the head of the table. The manual notes ROM runs slightly faster than
RAM for the same code, and that `002B` holds a `DJNZ $` for uncontended
timing loops.

## Testing paged code in this repo

`tests/bench.py` drives the Python `z80` module, which is a flat 64K. The
machine exposes **`set_output_callback(fn)`**, called as `fn(address, value)`
with the port in the low byte, so the paging registers can be emulated
exactly: keep physical RAM as a `bytearray`, and on a write to 250 or 251
copy the outgoing 32K back and the incoming 32K in. T-state counts stay
honest because the `OUT` is really executed.
