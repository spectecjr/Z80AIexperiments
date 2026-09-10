# storm.z80s — design notes

Distant thunder, and then rain, out of the two noise generators and
**not one tone enabled anywhere in the routine**. 3,153 T-states a
frame — 2.6% of a 50 Hz frame — for both at once.

Verified against `tests/storm.py` the way everything else here is —
**every OUT, in order, register and value, 7,013 of them** — and then
that captured stream is played through `tests/saa1099.py` to make
`demo/storm.wav`.

## Interface

| symbol | |
|---|---|
| `sm_init` | set the chip up, once |
| `sm_play` | start the storm |
| `sm_frame` | one 50 Hz frame of it |

Needs `saa.z80s` and `stormdata.z80s`
(`python3 tests/mkstormdata.py`).

## A noise generator is only hiss if you clock it fast

This is the whole routine. In **mode 3** the noise LFSR is clocked by a
tone generator rather than by one of the three fixed rates — and a tone
generator goes all the way down to 31 Hz. Clock the noise at a few
hundred shifts a second and what comes out is not hiss at all: it is a
random square wave, and all of its energy is below half the clock.

At 220 Hz that is a **rumble**. Measured on the wav, **81% of the
thunder is under 250 Hz** — 27% below 60, 35% between 60 and 125, 20%
between 125 and 250 — which is where real distant thunder sits.

And the sweep is the distance. The clock falls from 220 Hz to 78 Hz
across seven seconds, which is what the air does to thunder as it rolls
away: the top end goes first. Nothing about that is a filter — the chip
has no filter — it is one frequency register moving.

**The same generator at 5 kHz is rain.** Nothing else about it changes,
which is why the thunder's three channels can *change job*: once the
rumble has died they sweep up to 5.4 kHz and come back as the rain's
hiss, on one write to a frequency register.

## Three channels a layer, for the fade

An amplitude register is four bits, and sixteen steps is not enough to
fade a seven-second rumble without hearing it step down.

All three channels of a group carry the **same** noise generator, so
their outputs are identical and simply add: three channels at level 5
is exactly level 15, and the levels in between give **46 steps instead
of 16**. `sm_spread` holds the three amplitude bytes for each of those
46 levels, so a level is a lookup and never a division.

    ch0 ch1 ch2   noise generator 0, clocked by channel 0's tone
    ch3 ch4 ch5   noise generator 1, clocked by channel 3's tone

Each generator is clocked by the *first* channel of its group whichever
channel you listen to the noise on, so channel 0 and channel 3 are the
two clocks — and since no tone is enabled anywhere, both tone
generators are free to be exactly that and nothing else.

## The scores

Each layer is a list of segments — frames, octave, where the clock and
the level start, and an 8.8 step for each of them a frame — so a
seven-second sweep is **two 16-bit adds a frame and eight bytes of
table**. The accumulators are reloaded at each segment rather than
carried, so nothing drifts.

`tests/storm.py` writes them in Hz and 0..1 levels, and the generator
does the chip's bookkeeping — including **splitting any segment that
crosses an octave boundary**, because a frequency byte only spans one
octave: a sweep through 122 Hz ends at byte 0 of octave 2 and picks up
at byte 255 of octave 1, which is a 4-cent step and inaudible under a
rumble.

The thunder's score is eleven segments of swell and roll: up to full
over the first second and a half, then four decaying rolls, then a
tail. Measured: **peak at 1.6 seconds, four rolls after it**, and the
rain settling at about half the rumble's peak.

## What it costs

| | T-states | |
|---|---|---|
| `sm_frame` | **3,153** | 2.6% of a 50 Hz frame, both layers |
| `sm_init` | 1,152 | thirteen registers, once |

Ten register writes a frame, five a layer: the octave, the clock, and
three amplitudes. The tables are 176 bytes of score and 138 of spread.

## Invariants

- **No tone is ever enabled** (`0x14` stays zero). Enable one and the
  mixer changes what the noise does to that channel — `tone × (2 −
  noise)` rather than the noise on its own.
- A segment may not cross an octave boundary; the generator splits them
  and asserts it.
- The level accumulator is signed and can step below zero or above 45;
  the routine clamps at both ends before the lookup, and the model
  clamps identically.
- Both layers must run the same number of frames if they are to end
  together — they do, at 700.

## If you pick this up

1. **The crack of lightning.** A close strike is the opposite of this:
   a very fast attack, a bright noise burst (mode 0, 31.25 kHz) that
   decays in about 200 ms into the rumble. It wants an envelope faster
   than 50 Hz can draw, which is what the chip's own envelope
   generators are for — the one part of the SAA1099 nothing in this
   repo has used yet.
2. **Stereo.** Every amplitude byte here has the same level in both
   nibbles. Thunder is diffuse and rain is everywhere, so spreading the
   two layers apart — and letting them drift against each other —
   would cost nothing at all.
3. **Wind** is the third noise voice this chip does not have, but it is
   the same trick at 400-900 Hz with a slow random walk on the clock;
   it would have to share a generator with the rain.
4. **The rain could gust properly.** Its wash is a written score;
   driving the level and clock from an LFSR instead — `stars.z80s`'s,
   as `crow.z80s` uses it — would make it never repeat.

    python3 tests/mkstormdata.py    # the scores, from the Hz
    python3 tests/test_storm.py     # verify, time, and write the wav
