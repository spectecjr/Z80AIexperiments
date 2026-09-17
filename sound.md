# Sound in a frame that cannot be interrupted

**A SAA1099 wants feeding fifty times a second. These demos draw
twenty-five times a second with interrupts off from one end of the frame
to the other.** This is the plan for the tick that has to happen in
between, what each part of it costs — measured, in `tests/test_snd.py` —
and why it is scheduled rather than interrupted.

| | T-states | |
|---|---|---|
| the check, at a band that is not the one | **28** | 532 … 2,240 a frame, 19 bands to 80 |
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

**The window is about 100 µs, which is 600 T-states.** A poll that is
further apart than that misses a tick, and a missed tick is not a glitch
in the sound, it is the arrangement running slow. 600 T-states is half a
scanline of board: the check would have to go *inside* the row loop.

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

That is what makes a 70K register log affordable — it does not have to
fit in the 5.5K the resident block has spare. **The one thing to check on
real hardware** is that `LMPR` reads back what was written to it; if it
does not, the band loop keeps the current chunk in a cell instead and the
`IN` becomes an `LD A,(nn)`.

## The first tick is free, and so is the frame lock

The other tick a frame is the one at the top, and it costs nothing to
place: the frame has to wait for the display anyway to run at a steady 25
Hz, and that wait is the one place in the whole demo where `SP` is a
normal stack and nothing is half-drawn.

**Poll it there.** Bit 3 goes low for about 100 µs and then clears itself —
it does not latch until an interrupt is acknowledged — so a tight loop is
all it takes. Reading STATUS is about 30 T-states a turn, so the window is
twenty chances rather than one, and no interrupt is ever taken: `IM 1`
never has to be set up, the ROM's handler never runs, and the "interrupt
pushes `PC` into the picture" problem never arises anywhere in the demo.

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

**The one thing left to check on hardware** is the other direction of
`LMPR`: that it reads back what was written to it, so the tick can put the
band loop's chunk back without the loop having to keep a copy. If it does
not, the band loop stores the current chunk in a cell when it switches -
it already has the value in `A` at that point - and the `IN` becomes an
`LD A,(nn)`, which is two T-states cheaper anyway.

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

## Sound effects

An effect is another log, and the tick reads two. What it costs is the
pairs it writes — the same 80 T-states each — and what it costs *musically*
is a channel, which is the arrangement's problem rather than the frame's:
`chiparr.py` already chooses six voices out of a recording, and an effect
that wants one wants it taken off the arrangement first. The frame budget
has room for about ten more pairs a tick before sound reaches 2% of it.

    python3 tests/test_snd.py                 # the numbers above
