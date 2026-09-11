# ensemble.z80s — design notes

The shakuhachi and the string pad at once, **three oscillators each**,
out of one SAA1099: **3,360 T-states a frame, 2.8%, for two
instruments.**

Verified against `soundchip/tests/ensemble.py` — **every OUT, in order, 9,114 of
them** — and rendered to `demo/ensemble.wav`. Measured on what came
out: every note of both scores within **18 cents**.

| | |
|---|---|
| ch0 | the flute's breath |
| ch1 | the flute, f |
| ch2 | the flute, 2f |
| ch3 ch4 ch5 | the strings: root, third, fifth |

## Why the breath is on channel 0

Noise generator 0 serves channels 0 to 2, and in mode 3 it is clocked
by **channel 0's** tone generator — always the first channel of the
group, whichever channel you listen to the noise on. So the breath goes
on channel 0 with its *tone* disabled, which leaves that tone generator
free to be a 3.2 kHz clock and nothing else. Put the flute's
fundamental there instead and the breath would be clocked at the note:
a rumble, not air.

That is the sort of thing that decides a channel map, and it is only
visible if you know how mode 3 is wired.

## What three channels cost each voice

They lose different things, and only one of them matters.

**The flute loses 4f**, which was brightness and nothing else. It keeps
the breath and the vibrato, which are what make it a flute — and its
`f`/`2f` pair still costs one number, because an octave up is the same
frequency byte with the octave register one higher.

**The strings lose all three detuned twins**, and with them the 1 Hz
beating that made them a section rather than a chord. What is left is
the spread vibrato — one sine read at +0, +4 and +8 — so the three
notes still wander against each other, at 4 Hz rather than 1. It is
thinner. Six channels is what a string machine wants; three is what it
gets.

## The octave registers are the awkward part

Each octave register holds **two channels, a nibble each**, and the
split between the two voices falls inside register 0x11: its low nibble
is the flute's 2f and its high nibble is the strings' root. Two voices
that know nothing about each other have to write one byte between them.

The tables hold each nibble already shifted into place, so the frame is
three ORs:

    0x10 = 6 | (flute octave << 4)              the breath, and f
    0x11 = (flute octave + 1) | (root << 4)     2f, and the chord
    0x12 = third | (fifth << 4)

That is the whole of the interaction, and it is why this is one routine
rather than two that happen to run in the same frame.

## Fourteen registers, every frame

`shaku.z80s` and `strings.z80s` both work out what changed and write
only that. This does not: at two voices, deciding costs more than
writing, so every frame sends the same fourteen pairs — three octaves,
five frequencies, six levels — and the two voices' code does nothing
but fill them in. 3,360 T-states, against 1,554 and 1,097 for the two
alone.

The envelopes, the vibrato tables, the phrase and the chord lengths are
`shakudata.z80s`'s and `stringsdata.z80s`'s, unchanged; only the note
and chord tables are regenerated, because the octave nibbles land
somewhere else.

## If you pick this up

1. **The pad is the thin one.** If the flute could live on two channels
   (drop the breath to a fixed noise rate and share a generator) the
   strings could have four and get one detuned twin back — probably the
   best trade available.
2. **Panning is free and unused.** The flute centred and the pad spread
   would separate them without spending a channel.
3. **A third voice would have to come out of the pad**, and a bass note
   under it might be worth more than the fifth.

    python3 soundchip/tests/mkensembledata.py     # the repacked tables
    python3 soundchip/tests/test_ensemble.py      # verify, time, and write the wav
