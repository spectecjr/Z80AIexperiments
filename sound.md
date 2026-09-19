# Sound in a frame that cannot be interrupted

**A SAA1099 wants feeding fifty times a second. These demos draw
twenty-five times a second with interrupts off from one end of the frame
to the other.** This is the plan for the tick that has to happen in
between, what each part of it costs — measured, in `tests/test_snd.py` —
and why it is scheduled rather than interrupted.

| | T-states | |
|---|---|---|
| the check, at a band that is not the one | **28** | 532 … 2,240 a frame, 19 bands to 80 |
| *and on hardware, a register pair* | *+0 … 14* | *the SAA's ports are ASIC ports: see below* |
| a tick, nothing to say that frame | **185** | most frames of an arrangement change nothing |
| a tick, the median frame | 422 | two register pairs |
| a tick, the worst frame in three minutes | 2,662 | 31 pairs, 80 T-states each |
| **sound, mean** | **2,242** | 0.9% of a 25 Hz frame |
| **sound, worst** | **7,564** | 3.2%, and chequer10's worst frame goes to 95.8% |

## The problem is where, not how much

Sound is cheap here. `soundchip/` measures a live synthesiser at 1,097 to
3,360 T-states a frame and a register-log player at **212 T-states in the
mean frame** of a three minute arrangement, because most frames of music
change nothing. Two ticks a frame is under 1% of the budget.

What is expensive is that there is **nowhere to put it**. The frame runs
`DI` from beginning to end, and not by preference:

- `chq4_floor` holds `SP` on the screen for the whole board — the fill is
  `POP` from a table of six colour values and `PUSH` into the picture, at
  5.5 T-states a byte, and there is nothing faster on a Z80.
- the desert's two layers, the trees and the pilot are the same trick.
- an interrupt taken with `SP` on the screen **pushes `PC` into the
  picture**: two bytes of the frame become the return address, in a
  different place every time.

So the interrupt cannot be allowed to happen, and a 25 Hz frame is two
display frames long. One of the two ticks it owes belongs in the middle
of the drawing.

## Why not poll the status register

The obvious answer is to check STATUS (port 249, bit 3 low when the frame
interrupt is asserted) here and there through the drawing. It does not
work, for two reasons and they are both about the row loop:

**The window is 128 T-states.** SimCoupe clears the status bit and
schedules the clear-back `CPU_CYCLES_INT_ACTIVE` = 128 T later, which at 6
MHz is 21 µs rather than the 100 µs it is usually quoted at. A poll further
apart than that misses a tick, and a missed tick is not a glitch in the
sound, it is the arrangement running slow. 128 T-states is a third of a
scanline of board: the check would have to go *inside* the row loop,
several times a row.

**Inside a row loop there are no spare registers at all.** Both sets are
live — the row pointer, the mask pointer and the count in the alternate
set, the colour values in the main one — `IX` and `IY` are two of the six
values a `POP` fill reads, and `SP` is the screen. There is no register to
read STATUS into and no stack to save one on. The poll would cost more
than the tick it is looking for, several hundred times a frame.

The place polling *does* belong is the wait at the end of the frame — see
below. It is cheap there because that loop has nothing else to do.

## The frame is locked, so the tick can be counted

The frame is two display frames long and starts on a frame interrupt, so
the second tick belongs **120,000 T-states in**. Every band of the board
costs a known number of T-states — that is what `reports/` is — so the
caller knows *which band* that is before it starts, and pokes the number.

    snd_n = the band the tick belongs in, from the horizon

Nothing is polled and nothing can be missed. The count of ticks a second
is exactly right by construction, and any error in *where* the tick lands
is re-zeroed by the interrupt at the top of the next frame, so it cannot
accumulate. The error itself is contention — the schedule is in raw
T-states and a real SAM's ASIC steals cycles while the display is being
fetched — which at the worst is a band's width of drift, under a
millisecond on a 20 ms tick. Inaudible on a chip whose envelopes step at
this rate anyway.

## The band loop's top is the one free seam in the frame

Inside a row every register is live. **At the top of a band almost nothing
is**: `chq4_b1` reloads `HL` from the band table, `A`, `DE` and `BC` from
cells, and `SP` is dead until the next row sets it — so the main set,
`IX`, `IY` and `SP` are all free there. Only the alternate set survives a
band boundary.

Which means a tick that stays in the main set **needs no saving at all**:

```
chq4_b1:
        LD   HL,snd_n           ; 10      the whole of the check
        DEC  (HL)               ; 11
        JR   Z,snd_fire         ; 7 not taken - and not taken is the
                                ;   band loop carrying straight on
```

28 T-states a band, 532 at the shallowest horizon and 2,240 at the
deepest. When it fires:

```
snd_fire:
        LD   SP,snd_stack       ; SP is dead here
        CALL snd_tick
```

and the tick returns into the band loop with the alternate set untouched.
A player that uses `EXX` has to put the alternate set back; `snd.z80s`
does not use it.

**Its stack has to be in the high block.** The caller's own stack lives in
chunk 0 at `7FF0`, and chunk 0 is paged away for most of the frame — the
low block is whichever run chunk the band loop is drawing out of. Eight
levels in the resident block is enough and costs sixteen bytes.

**And the tick owns the low block for its duration.** The screen is in the
high block and so is this code, so the low 32K is the run bank and nothing
else: the tick can page its log in over it and put the chunk back, which
is two `OUT`s and a byte:

```
        IN   A,(250)            ; whichever chunk the band loop has in
        LD   (snd_back+1),A
        LD   A,SND_BANK
        OUT  (250),A
        ...
snd_back:
        LD   A,0                ; patched
        OUT  (250),A
```

That is what makes a 70K register log affordable — it does not have to fit
in the 5.5K the resident block has spare. **And `LMPR` does read back what
was written**, so the tick needs no help from the band loop to put the chunk
back: all three paging registers are read/write, and VMPR is the only one
whose bit 7 means something different on read (MIDI receiving) from on
write.

## The first tick is free, and so is the frame lock

The other tick a frame is the one at the top, and it costs nothing to
place: the frame has to wait for the display anyway to run at a steady 25
Hz, and that wait is the one place in the whole demo where `SP` is a
normal stack and nothing is half-drawn.

**Poll it there.** Bit 3 goes low for 128 T-states and then clears itself —
it does not latch until an interrupt is acknowledged — so a tight loop is
all it takes. Reading STATUS is about 30 T-states a turn, so the window is
four chances rather than one, and no interrupt is ever taken: `IM 1` never
has to be set up, the ROM's handler never runs, and the "interrupt pushes
`PC` into the picture" problem never arises anywhere in the demo. **Keep
that loop tight**: it is four chances, not twenty, and `IN A,(249)` is an
ASIC port so it pays up to 7 T-states of its own waiting for an 8 T
boundary.

```
snd_wait:
        IN   A,(249)
        AND  8                  ; frame, and it is low when asserted
        JR   NZ,snd_wait
        CALL snd_tick           ; the top of the frame
```

**And the same loop is the frame lock.** A poll that has to *wait* for the
bit is a demo running at a steady 25 Hz; one that finds it already low has
overrun its two display frames and knows it. That is a frame counter for
nothing, which is the other thing a demo wants and the reason not to
measure the lock by counting T-states.

**And `LMPR` does read back what was written**, so the tick can put the band
loop's chunk back without the loop having to keep a copy - confirmed by the
machine's owners and by SimCoupe, which returns `m_state.lmpr` unmodified.
All three paging registers are read/write; VMPR is the only one whose bit 7
means something different on read (MIDI receiving) from on write.

## When the frame is short, there is no mid-frame tick to place

At the shallow horizons the whole frame is 95,951 T-states — less than one
display frame — so both ticks can happen outside the drawing: one at the
top, one in the wait. The mid-frame tick is only needed when the frame
runs past 120,000 T-states, and when it does, the board is the piece that
put it there: 124,066 T-states of the 222,452 in chequer10's worst frame.
**So one seam covers every case.** Between the two there is a band of
frames where the halfway point falls in the desert or the trees instead;
the honest answer there is to let that tick wait for the end of the
drawing, which puts it a few thousand T-states late — half a millisecond,
against seams in three more routines.

## What it costs the demo

| | |
|---|---|
| `chequer10`, worst frame now | 222,452 — **93%** of a 25 Hz frame |
| with sound, mean | 224,694 — 93.6% |
| with sound, its worst frame too | 230,016 — **95.8%** |

The worst case stacks the deepest board, the biggest trees and the
arrangement's own worst frame, twice over, and it still fits. The mean is
2,242 T-states, which is **0.9%**.

**Which is the argument for a register log over a live synthesiser.**
`soundchip/`'s `ensemble` is 3,360 T-states *every* frame and would cost
6,720 a frame here — three times the mean of a log that rewrites only what
changed. See `soundchip/chiparr.md` for how a recording becomes one.

## What it costs on the real machine

Every figure above is uncontended. Two things change on hardware, and they
pull the same way:

**The SAA's ports are ASIC ports.** The data port is 255 and the register
select is 511, both with 255 in the low byte, so both are above SimCoupe's
`BASE_ASIC_PORT` of 248 — and an ASIC port access waits for an 8 T-state
boundary *wherever the raster is*, border and display alike. A register
pair is two `OUT`s, so it pays **0 to 14 T-states** on top of `saa.z80s`'s
measured 74, and the worst frame of an arrangement pays it 31 times: 2,662
T-states becomes up to 3,096. Still under 1.3% of a 25 Hz frame.

**And the tick's own memory accesses cost slots like everything else.** The
mid-frame tick lands inside the board, which is the contended part of the
frame, so its 185 to 2,662 T-states are close to `accesses x 8`. It does
not change the conclusion — the tick is under 1% of the frame either way —
but it is the reason not to spend the saving on a fatter player.

## Sound effects

An effect is another log, and the tick reads two. What it costs is the
pairs it writes — the same 80 T-states each — and what it costs *musically*
is a channel, which is the arrangement's problem rather than the frame's:
`chiparr.py` already chooses six voices out of a recording, and an effect
that wants one wants it taken off the arrangement first. The frame budget
has room for about ten more pairs a tick before sound reaches 2% of it.

    python3 tests/test_snd.py                 # the numbers above
