# crow.z80s — design notes

A crow cawing out of one SAA1099, from twelve register writes a 50 Hz
frame. **1,654 T-states while it is cawing — 1.4% of a frame** — and 55
when it is not.

No samples and no streaming: six tone generators, one noise generator
and the amplitude registers, and the CPU touching them fifty times a
second.

Verified against `soundchip/tests/crow.py` the way everything else here is
verified — **every OUT the routine makes, in order, register and value,
over 1,960 writes** — and then the captured write stream is played
through `soundchip/tests/saa1099.py` to make `demo/crow.wav`. What you listen to
is the Z80's own output, not a Python impression of it.

## Interface

| symbol | |
|---|---|
| `crow_init` | silence the chip and set up the voice, once |
| `crow_call` | caw — three of them, and no two calls alike |
| `crow_frame` | one 50 Hz frame of whatever is going on |

## The problem, and the one idea

A caw is a harsh falling *kaaa* of about a third of a second. Harsh is
the hard part. What makes a voice sound rough rather than sung is
amplitude modulation at a few tens of hertz — a crow's syrinx beats
against itself at around 40 Hz — and **a routine that runs at 50 Hz
cannot modulate anything at 40 Hz.** Writing amplitudes gets you 25 Hz
before Nyquist stops you, and it sounds like a stutter, not a voice.

**Two oscillators a semitone apart do it for nothing.** Put a second
tone generator 40 Hz below the first and the pair beat at 40 Hz — in the
chip, at audio rate, for one extra register write a frame and no CPU
time at all. The modulation is a *property of the sound*, not something
the control rate has to carry. That is the whole design:

| | |
|---|---|
| ch0 | `f`, the fundamental — 400 to 470 Hz across a call |
| ch1 | `f − 40 Hz` — the beat, and the roughness |
| ch2 | `2f`, the second harmonic |
| ch4 | `2f − 47 Hz` — so the harmonic is rough too, which is what stops it sounding like a chord |
| ch5 | `4f`, four levels down: a little brightness |
| ch3 | noise, and the rasp |

Two more things fall out of the chip's own arithmetic:

**An octave up is the same frequency byte.** `f = 15625 × 2^oct /
(511 − n)`, so doubling the frequency is `oct + 1` with `n` unchanged.
The octaves are set once by `crow_init` and never written again, and
`2f` and `4f` cost the routine nothing but the store — no multiply, no
second table, no rounding.

**The noise can be pitched.** Noise generator 1 in mode 3 is clocked by
channel 3's *tone* generator instead of a fixed 31.25/15.6/7.8 kHz, so
the rasp has a pitch — and it sweeps, from 3.8 kHz at the attack down to
2.4 kHz with everything else. A fixed-rate noise generator sounds like
tape hiss over the top of a tone; a swept one sounds like part of the
bird.

## What a frame does

`crow_env` is eighteen rows of four bytes — frequency, noise clock, tone
level, noise level — one row a frame, 360 ms of caw. The frame reads its
row, adds this caw's transpose to the frequency, subtracts this caw's
level drop from both amplitudes, and stores twelve values into a table
of (register, value) pairs that `crow_send` blasts out.

A call is three caws out of `crow_seq`, each transposed up a little and
dropped a level or two, with a 0-3 unit jitter off `stars.z80s`'s LFSR so
that no two calls are the same. Between them are twelve frames of
silence, which puts a caw every 0.6 seconds.

**The ports.** The SAA1099 on a SAM is register-select at 511 and data
at 255 — both with 255 in the low half of the address. So `C` holds 255
for the whole run and `B`, which the Z80 puts on the top half of the
address bus for `OUT (C),A`, is 1 to select a register and 0 to write
it. A pair of writes is ten bytes of code with no reloading:

    LD B,1 / LD A,(HL) / INC HL / OUT (C),A
    LD B,0 / LD A,(HL) / INC HL / OUT (C),A

**No clamping anywhere.** Both detunes are downwards and every transpose
is upwards, so the highest byte the routine can write is the top of the
pitch arc transposed up and the lowest is the bottom of it detuned down.
`soundchip/tests/crow.py` asserts both ends, which is why the frame code can add
and subtract without checking.

## What it costs

| | T-states | |
|---|---|---|
| `crow_frame`, cawing | **1,654** | 1.4% of a 50 Hz frame |
| `crow_frame`, silent | 55 | |
| `crow_frame`, starting a caw | 784 | the LFSR, once a caw |
| `crow_init` | 1,419 | sixteen registers, once |

Data is 72 bytes of caw, 6 of call and 32 of init; code is about 200.

## What came out

Measured on the rendered wav, over the first caw:

| | |
|---|---|
| energy 300-600 Hz | 36% |
| 600-1200 Hz | 36% |
| 1200-2400 Hz | 13% |
| 2400-4800 Hz | 8% |
| roughness | **38 Hz, 35% deep** |

Which is the shape a corvid caw has: most of it in the fundamental and
the second harmonic, a tail of noise above, and a voice that is rough
rather than clean. `soundchip/tests/test_crow.py` prints a spectrogram of the
first two calls in the terminal, so the three caws and their falling
pitch can be seen without opening anything.

**I cannot hear it.** Everything above is measurement, and the design
came from what a crow's spectrogram looks like rather than from
listening. If it wants tuning, the whole voice is the `CAW` table at the
top of `soundchip/tests/crow.py`, in Hz and 0-15 levels — change it there, run
`python3 soundchip/tests/mkcrowdata.py` and then `soundchip/tests/test_crow.py`, and the
table, the assembly's data file and the wav all follow.

## What the emulation assumes

`soundchip/tests/saa1099.py` is a renderer, not something verified against
hardware. The Z80 side is exact; the chip side follows **SAASound**
(which is what SimCoupe plays) and MAME, and these are the places where
that mattered:

- **clock 8 MHz**, so `f = 15625 × 2^octave / (511 − n)`, 31 Hz to
  7.81 kHz.
- **noise**: an 18-bit LFSR, `x^18 + x^11 + x`, seeded with 1 and
  shifted right — `rand = (rand >> 1) ^ 0x20400` when the bit shifted
  out is 1. Modes 0-2 shift it at 31250, 15625 and 7812.5 Hz.
- **mode 3** takes its clock from the tone generator of channel 0 or 3,
  which triggers it once per half cycle — so at **twice** that channel's
  audible frequency.
- **the mixer**: tone alone or noise alone gives the amplitude when the
  bit is 1. With both enabled on the same channel the output is
  `tone × (2 − noise)`: full on a tone 1 with the noise low, half on a
  tone 1 with the noise high, nothing when the tone is low. This routine
  never enables both on one channel, so that path does not affect the
  wav.
- **envelope generators are not implemented** — writing bit 7 of 0x18 or
  0x19 raises rather than pretending. The routine sets both registers to
  zero.
- The rendering runs at 4× and filters down, so the squares do not
  alias, and the output is DC-blocked because the chip's output is
  unipolar and a SAM's audio out is not.

## If you pick this up

1. **The other five channels.** Nothing here uses the second noise
   generator, the envelope generators, or the stereo — every amplitude
   byte has the same level in both nibbles. Panning the detuned partner
   away from the fundamental would widen it, at the price of the beat
   happening in the room rather than in the mix.
2. **The envelope generators would buy a better attack.** They run off
   frequency generator 1 or 4, so they modulate at audio rate rather
   than frame rate: a fast decay on the noise channel is what the "k" of
   the caw really wants, and 50 Hz cannot draw it.
3. **Other corvids are the same routine.** A raven is the same voice a
   fourth lower and slower (octave 3 has room down to 245 Hz); a jackdaw
   is shorter, higher and less rough — fewer frames, less detune.
4. **It is a synth, not a sample player.** Anything that wants a voice —
   an engine, a beast, a door — is another `CAW` table and the same
   fourteen bytes of state.

    python3 soundchip/tests/mkcrowdata.py     # the tables, from the Hz
    python3 soundchip/tests/test_crow.py      # verify, time, and write demo/crow.wav
