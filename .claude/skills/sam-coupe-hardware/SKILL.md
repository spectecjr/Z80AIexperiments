---
name: sam-coupe-hardware
description: The SAM Coupé's ports, memory paging and screen modes, as the demos in this repo need them - LMPR/HMPR/VMPR paging and what it means for a memory map, the CLUT and its port-addressing trap, the line interrupt, the border, and contention. Use when writing or changing a routine that pages memory, double buffers, flips the palette, or budgets a frame.
---

# The SAM Coupé, for this repo

Source: the SAM Coupé Technical Manual
(github.com/stefandrissen/sam-coupe-technical-manual), the machine's owners,
and SimCoupe's source where a number had to be exact. A few things the
manual does not state outright are still marked *inferred*.

## The machine

- Zilog Z80B at 6 MHz. A frame is **119,808 T-states** - 384 a line, 312
  lines, 50.08 Hz. Ignoring memory contention that is what the CPU gets
  between 50 Hz interrupts; `costs.md` budgets against a round **120,000,
  and 240,000 at 25 Hz**, which is 0.16% out and never the thing that
  decides anything. **Real budgets are lower**, and the number that decides
  is not T-states at all: see Contention.
- 256K fitted as standard, 512K with the internal expansion, addressed as
  **32 pages of 16K**. Nearly all users have 512K of memory.
- The lower 5 bits of a paging register pick the page,
  so a 256K machine uses pages 0-15.
- The Z80's 64K is four 16K **sections**: A `0000`, B `4000`, C `8000`,
  D `C000`. A+B is the **low block**, C+D the **high block**.
- Up to 4MB of external memory, available as up to four 1MB modules. Each module has
  a hardware ID from 0-3, which form the upper 2-bits of a 16KB page register. Ownership of
  external memory modules is much rarer. 
- External memory can be paged into sections C+D only.
- Sound is played through a Philips SAA1099 6-channel sound chip
- The disk controller is a WD1772 chip; there are 0-2 of these in each machine. It's reasonable
  to assume that there is at least one per system. SAM disks normally have 80 tracks, 2 sides, and
  10 x 512-byte sectors per track - although some schemes increase the capacity beyond this.
- Other hardware includes a comms chip, and a realtime clock which can act as a high-frequency
  timer, a mouse, joysticks (mapped to keyboard keys), a lightpen/light gun, and a parallel/printer
  port.

### The CPU

The Z80B is an in-order execution CPU with a single combined IO/Memory bus but two IO/Memory
address spaces. It has no cache; all memory operations occur directly to main memory.

On the SAM Coupe the CPU has to share memory access with the main system control module
(the ASIC), which needs to access memory to isochronously update the display and to
refresh the DRAM.

As the system is intended to simulate a ZX Spectrum in one of its graphics modes, it must 
emulate that system's CPU speed as well. The ZX Spectrum had a 3.5MHz Z80A CPU, so in graphics
mode 0 (ZX Spectrum compatible - **MODE 1** in the user-facing numbering,
since VMPR encodes `mode - 1`) it slows the system down by inserting extra
wait cycles, roughly reducing the speed of the CPU by half. That is exactly
what the contention table shows: MODE 1 contends in 64-cycle bands outside
the display as well as inside it, which no other mode does.

## The Display

The raster, which everything about timing hangs off:

| | |
|---|---|
| a line | **384 T-states** - 64 border, **256 active display**, 64 border |
| a frame | **119,808 T** over **312 lines**, 50.08 Hz |
| the display | lines **68 to 259**: 68 blanked lines above it, 52 below |
| `t = 0` | **the frame interrupt**, 68 lines before the display starts |

8 T-states a cell, 48 cells a line, 8 of them side border each side. Those
numbers are where the contention table comes from and where the light pen
registers read from, so they are worth having in one place: **Contention**
below works out what they cost, and **Reading the current raster position**
is how a program finds out where it is.

## Internal Memory Paging - LMPR (250) and HMPR (251)

**LMPR** pages the low block, **HMPR** the high block, and the rule that
shapes every memory map is:

> the second section of a block is *always* the page above the first.

Note that **LMPR** and **HMPR** can both have sections overridden with 16KB regions of the 32KB
ROM. 

Section A can be selected to present either ROM0 or RAM.
Section D can be selected to present ROM1, Internal Memory or External memory.
Section C can be selected to present Internal Memory or External memory.
The external/internal memory selector for sections C and D applies to both C and D.
In order of priority, ROM > External Memory > Internal Memory.

**Apply that per section**, taking the highest-priority source that is
*enabled for that section*. So with `LMPR` bit 6 (ROM1) set and `HMPR` bit 7
(MCNTRL) set:

| section | what is enabled | what wins |
|---|---|---|
| A | ROM0 unless RAM0 is set | ROM0, or internal |
| B | internal only | internal, always the page above A |
| C | external (MCNTRL), internal | **external** |
| D | ROM1 (LMPR bit 6), external (MCNTRL), internal | **ROM 1** |

**⚠ SimCoupe resolves section D the other way round**, and one of the two is
wrong. `Base/SAMIO.cpp`'s `UpdatePaging()` tests external *before* ROM 1:

    // External RAM, ROM1, or internal RAM in section D
    if (m_state.hmpr & HMPR_MCNTRL_MASK)  PageIn(Section::D, EXTMEM + hepr);
    else if (m_state.lmpr & LMPR_ROM1)    PageIn(Section::D, ROM1);
    else                                  PageIn(Section::D, (hmpr + 1) & 31);

so it gives **external memory** for D where the rule above gives ROM 1. Its
own comment lists the precedence as "External RAM, ROM1, or internal RAM".
Everything else about the two agrees: section A is ROM0 unless RAM0, C and D
take `LEPR` (128) and `HEPR` (129) independently when MCNTRL is set, and the
pair rule holds.

**The rule to code to, whichever it turns out to be: never set ROM1 and
MCNTRL at the same time.** Clear `LMPR` bit 6 before enabling external
memory, and section D is unambiguous under both readings. That is correct
either way and costs nothing, because a program that wants 64 pages of
external RAM in the high block is not also running out of ROM 1.

And if the corner cannot be avoided: **SimCoupe's answer is the one that
will happen in practice**, because that is what the code will be run and
tested on. The question is out with the SAM developer community; when it
comes back this note becomes one line either way.

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

**LMPR, HMPR and VMPR are all read/write**, and LMPR and HMPR read back
exactly what was written - so a routine can save and restore the caller's
paging rather than assuming it, and a routine called from inside someone
else's paged window can put their page back without being told what it was.
**VMPR is the one register whose bit 7 changes meaning between read and
write**: written it is MIDI, read it is "MIDI receiving". Mask it before
using a value read back from VMPR - `chequer9`'s buffer flip reads HMPR and
`AND 31`s it for the same reason.

Page numbers for LMPR, HMPR wrap - that is, if LMPR is set to page 31 (with RAM0 enabled), section
A will contain page 31, and section B will contain page 0.

Similarly, HMPR set to 31 will leave page 31 in section C, and page 0 in section D.

## External Memory Paging

XMEML (128) and XMEMH (129) both control the external memory pages presented in
sections C + D when MCNTRL (external memory enabled when high) is set.

XMEML and XMEMH are both independently addressible, and both are used
to index a 16KB memory page.

- XMEML controls section C
- XMEMH controls section D

| | Page |
|---|---|
| bits 0-5 | Page number within a 1MB module |
| bits 6-7 | 1MB module number (set with a jumper on the board) from 0-3 |

### Testing for external memory presence

While MasterDOS and MasterBASIC both maintain a page allocation table for external memory for
application use, most games and demos avoid using this and take over all of memory for
themselves.

Most games/demos therefore need to identify what memory is present on the machine.

Typically internal memory is assumed (512k), but external memory is probed by cycling through the
port numbers and reading/writing values in a loop. If the CPU can successfully write and 
read back a variety of values (not just 0x00 and 0xff), it can be assumed to be present. This
is then repeated for each page until an idea of the external memory available on the device
has been built up.

For games and demos it's not unreasonable to expect a maximum of one single module, the only
question then is what its jumper has been set to, which requires four probes to determine.

## The screen - VMPR (252)

- bits 0-4: the page the **video hardware** displays. bits 5-6: MDE0/MDE1,
  the screen mode. bit 7 is MIDI, not video - and it is the one bit in any
  of the three paging registers that means something different on read
  (MIDI receiving) from on write.
- *Inferred*: the mode bits are `mode - 1`, so MODE 4 is `0x60 | page`. The
  manual gives MDE0/MDE1 only as "first/second bit of screen mode control",
  but the ROM's `JMODE` takes 0-3 for MODEs 1-4.
- **MODE 4**: 256x192, 16 colours from 128, 4 bits a pixel, high nibble is
  the *left* pixel of the two, 128 bytes a line, **24,576 bytes** a screen.
  MODE 3 is 512x192 in 4 colours over the same 24K (two bits in HMPR select
  the palette section to use for pixels emitted in mode 3; they're effectively
  substituted in as the upper two bits of the CLUT index for each pixel).
- A 24K screen crosses a page boundary, so **the video page must be even**:
  the hardware wraps from the even page into the odd one above it, always
  within the same pair. (In hardware, bit 0 of VMPR is ignored in modes 3/4).
- A screen therefore leaves **8K spare** at the end of its odd page. The ROM
  uses it as scratch (`JGRAB`, `JFILL`); a demo can put code or tables there.

**The displayed page does not have to be mapped into the CPU's address
space.** VMPR points the display hardware straight at RAM. Double buffering
costs 24K of address space, not 48K: map the back buffer, draw, then flip
with one `OUT` to VMPR and one to HMPR.

## Interrupting at different points within a frame

- There is a 50Hz frame interrupt.
- Line interrupts can be configured by writing the line number they should trigger on to
  the LINE INT registers (0xF9) and the interrupts occur in the border area at the end of the previous line. Line interrupts can be disabled by writing any value between 192-255 to the
  line interrupt register. 
- MIDI can also be used to provide a 16.5kHz interrupt, by continuously writing data to it.

## Reading the current raster position

It's reasonable to assume that no user has a lightpen - they were either never created
for the system, or are so rare that they're never found.

The light pen - when connected - latches the raster X and Y position in the display
when the raster passes the tip of the light pen. When one is not connected, the
HPEN and LPEN registers can be used to read the X and Y position of the current
display being generated.

The current line number (Y value) is available by reading HPEN (&01F8).
The current horizontal position (X value) is available by reading LPEN (&00F8).

The two LSB of LPEN must be masked off.

**They are read at 248 and 504, which is the CLUT's own port pair** - the
CLUT is write-only there and the light pen registers are what a *read*
returns. So the CLUT's addressing trap applies in reverse: `IN A,(248)`
puts **A** on the high address byte and therefore reads HPEN or LPEN
depending on what happens to be in A. Use `LD BC,0x01F8 : IN A,(C)` for the
line and `LD BC,0x00F8 : IN A,(C)` for the position.

**And they are ASIC ports**, so each read waits for an 8 T-state boundary
like every other port at 248 or above (see Contention) - which is not a
problem for what they are good for.

**What they are good for is measuring time on real hardware.** Read HPEN
before a routine and after it and the difference in lines is its cost, at
384 T-states a line; LPEN gives the position within the line to 4 T-states,
so the pair is a cycle counter with no debugger, no instrumentation and no
emulator. That is the measurement `game.md` and `costs.md` want in order to
confirm the contention model against a machine: bracket `cq10_frame` with
two reads and compare.

| | LPEN (0x00F8) |
|---|---|
| bit 7-2 | bits 7-2 of the X coordinate of the raster (you must treat bits 1-0 as zero by masking) |
| bit 1 | Set if MIDI is being transmitted (busy) |
| bit 0 | Bit 0 of the CLUT index for the pixel being written to the display |

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
purpose rather than discovering. `chequer9` needs twenty-four, because a
horizon that moves has to have every square width it can ever show compiled:
the pages are where the cost of that lands, not the frame.

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
  the one written, 0-191; write 192-255 to disable. Exactly: it fires at
  frame cycle `(line + 68) * 384`, the start of that display line, because
  the display starts 68 lines after the frame interrupt (see Contention). This is the only
  mid-screen palette or mode change, and it is always enabled.
  `road2.md` measures what it costs: ~150 T-states a line with entry and
  exit, **28,800 a frame over 192 lines**, and it cannot fire at all during
  a `PUSH` fill, because the fill holds `SP` on the screen and an interrupt
  would push `PC` into the picture. **That is a quarter of a 50 Hz frame for
  a screen of palette changes, and it wants interrupts enabled, so a
  routine that draws through `SP` cannot have both.** `chequer9` is the
  demo that took the consequence: no per-scanline palette at all, sixteen
  colours for the whole screen, and the distance carried by the geometry.
- **STATUS (249, read)**: bit 0 line, bit 1 mouse, bit 2 MIDI in, **bit 3
  frame**, bit 4 MIDI out - each *low* when requesting. Bits 5-7 are
  keyboard matrix lines 6-8. All five interrupts share IM 1, so the handler
  has to read this to know which fired.
- **A request is held for 128 T-states and then clears itself**, rather
  than latching until an interrupt is acknowledged - SimCoupe's
  `Base/Events.cpp` clears the status bit on `FrameInterrupt` and sets it
  again on `FrameInterruptEnd`, scheduled `CPU_CYCLES_INT_ACTIVE` = 128 T
  later, and the line interrupt behaves the same way. **128 T-states is
  21 µs**, not the 100 µs it is often quoted at. So a routine that runs
  `DI` from end to end can *poll* this register instead of ever taking an
  interrupt - but only from a loop tight enough to look four or five times
  in 128 T-states, which a wait loop is and the inside of a fill is not.
  That is the whole of the argument in `sound.md` for scheduling a
  mid-frame music tick and polling only for the frame lock.

## Contention, and the table SimCoupe builds

**The currency on a SAM is memory accesses, not T-states.** The ASIC shares
one bus between the CPU and the display and lets the CPU through only on a
boundary: every 8 T-states while the raster is in the active display, every
4 T-states everywhere else. `costs.md` §1b and `game.md` work out what that
does to a frame; this is the table itself, transcribed from SimCoupe, which
is cycle accurate and whose author developed it against the machine
(`Base/Memory.cpp`, `Base/SAMIO.h`, `Base/SAM.h`).

**The geometry.** 8 T a cell, 48 cells a line, 8 of them side border each
side:

| | |
|---|---|
| a line | **384 T** - 64 border, **256 active display**, 64 border |
| a frame | **119,808 T** over **312 lines**, 50.08 Hz |
| screen lines | 68 to 259; 68 above, 52 below |
| **slots a frame** | **23,808** = 192 x (32 + 32) + 120 x 96 |

**`t = 0` is the frame interrupt**, and the display does not start until line
68. So the frame goes: interrupt, **68 blanked lines**, 192 display lines, 52
blanked lines, interrupt. Which gives a scheduling rule worth having:

| after the frame interrupt | T-states | slots |
|---|---|---|
| **68 blanked lines, before the raster reaches the display** | 26,112 | **6,528** |
| 192 display lines | 73,728 | 12,288 |
| 52 blanked lines | 19,968 | 4,992 |

**48% of a frame's slots are in the 38% of it that is blanked.** Work done
in the first 26,112 T-states after the interrupt costs 4 T an access rather
than 8 - so a routine with a heavy, order-free phase (a fill, a clear, a
table build) should do it *first*, and a routine that draws top-down is
already doing the right thing by accident.

**The memory table.** For a frame cycle `t`, the wait before the access is

    line       = t / 384
    line_cycle = (t + 4) % 384                  ; CONTENTION_OFFSET is 4
    main       = 68 <= line < 260 and line_cycle >= 128
    mask       = main ? 7 : 3                   ; MODE 2, 3 and 4
    delay      = mask - ((t + 2) & mask)

so well inside the display window an access can only happen at
`t == 5 (mod 8)`, and outside it at `t == 1 (mod 4)`; the first access after
the window opens can still land on the old phase. The `+ 2` is where in the
machine cycle the bus is actually used - it shifts the phase and does not
change the rate. An instruction therefore costs
**`max(natural_T, accesses x slot_width)`**, and during the display almost
everything costs `accesses x 8`:

| a `PUSH DE` in a run of them | | |
|---|---|---|
| uncontended | 11 T | 5.5 T a byte |
| in the border or a blanked line | `max(11, 3 x 4)` = 12 T | 6.0 T a byte |
| **in the display** | `3 x 8` = **24 T** | **12.0 T a byte** |

| and the three tables | mask |
|---|---|
| MODE 2/3/4, in the display | 7 |
| anywhere else, and the whole frame with the screen off | 3 |
| **MODE 1** | 7 in the display *and* in 64-cycle bands outside it (`!(line_cycle & 0x40)`) - it is the worst mode, not the cheapest |

**Only internal RAM is contended.** `afSectionContended[section] = (page <
NUM_INTERNAL_PAGES)`, so ROM and external (megabyte) memory take **no waits
at all** - which is why the manual notes ROM runs slightly faster for the
same code.

**Which is the most interesting consequence in this file.** External memory
pages into sections C and D (see External Memory Paging), and a compiled
sprite or run bank is mostly *instruction fetches* - the dominant slot cost
in everything this repo does. A bank held in external RAM is fetched without
contention even while the raster is in the display, where internal RAM would
cost 8 T-states an access. It also lifts the 512K ceiling the map has been
budgeted against: `game.md` counts pages out of the 32 that LMPR can
address, and an external module is 64 more of them for data that does not
need to be in the low block. Neither this nor the 4 MB it allows has been
measured here - and the catch is that C and D are exactly where this repo's
maps put the screen and the resident code, so using it means rearranging the
map rather than just adding to it.

**SOFF does not remove contention**, it removes the display window's share:
a blanked frame uses the 4 T table throughout, **29,952 slots rather than
23,808**, so a precompute with the screen off is 26% better off and not
unbounded.

**And the ASIC ports are contended everywhere in the frame**, wherever the
raster is:

    if ((port & 0xFF) < 0xF8) return 0;         ; BASE_ASIC_PORT
    delay = 7 - ((t + 2) & 7);

Ports 248 upward are all of them: **CLUT (248), STATUS and LINE INT (249),
LMPR (250), HMPR (251), VMPR (252), BORDER and KEYBOARD (254) - and the
SAA1099's data port at 255 and register select at 511.** Every palette
write, every paging switch and every sound register pays up to 7 T-states
waiting for an 8 T boundary, in the border as much as in the display. Ports
below 248 are free.

**What it comes to**, for the write primitive this repository is built on:
a `PUSH` is 3 accesses for 2 bytes, so the ceiling on screen writes is
**15,872 bytes a frame against a 24,576 byte screen**. A full-screen
`PUSH` fill is 1.55 frames and there is no arrangement of code that makes
it one.

**Which page is mapped where does not change any of this** - the tables are
indexed by frame cycle, not by address - but *what kind of memory* does, per
the paragraph above: internal RAM contends, ROM and external memory do not.
So a routine's access count does not change because it pages, and its cost
changes only if it pages something that is not internal RAM. `tests/sam.py`'s `traffic()` counts a routine's
accesses and `tests/mkbudget.py` divides them by 23,808; measured across
chequer10 that is **a third more than the T-state count says**. `002B`
holds a `DJNZ $` for uncontended timing loops.

## Testing paged code in this repo

`tests/bench.py` drives the Python `z80` module, which is a flat 64K. The
machine exposes **`set_output_callback(fn)`**, called as `fn(address, value)`
with the port in the low byte, so the paging registers can be emulated
exactly: keep physical RAM as a `bytearray`, and on a write to 250 or 251
copy the outgoing 32K back and the incoming 32K in. T-state counts stay
honest because the `OUT` is really executed.

## Joysticks

Joysticks 0 and 1 are mapped to keys 6,7,8,9,0 and 1,2,3,4,5. The mappings are:

| Direction | Joystick 0 | Joystick 1 |
|-----------|------------|------------|
| Left | 6 | 1 |
| Right | 7 | 2 |
| Down | 8 | 3 | 
| Up | 9 | 4 |
| Fire | 0 | 5 |

## Demo configuration

For the most part, to run a demo, the binary should be loaded into page 1 upwards, at origin
32768, and called at that address (&8000) by BASIC. 

For a basic program, this looks like:

10 LOAD "code" CODE 32768
20 CALL 32768

On entry, paging is set up as follows:

Section A - ROM 0
Section B - the system page (page 0)
Section C - Page 1
Section D - Page 2 (ROM1 paged out)

The stack will be in the range &4000-7FFF.

The demo must then in response:

1. Disable interrupts.
2. Adjust the stack.
3. Set up paging, trampolining down to section A-B if necessary (especially if interrupts must
   be serviced regularly). (Note: It's okay to stay in 0x8000-0xffff if necessary).
4. If interrupts are needed, re-enable them.
5. Run the demo code.

It's okay to assume that a user must press the RESET button to reboot the machine to get out of
a demo. It's also okay to assume that they don't have MIDI or Lightpen hardware plugged in, 
they have at least a single disk drive, and that they will never press the NMI button while
the demo is running (or that corruption/crashing is acceptable in that case).

If needed the system page can be used as memory after the demo takes control, but this should be
avoided unless memory is scarce as it's more complexity.
