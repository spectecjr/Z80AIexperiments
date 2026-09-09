# mkgif.py — design notes

Records the renderers running on the emulated Z80 as animated GIFs, one
file per demo, and checks each file by reading it back with a decoder that
had no part in writing it.

    python3 tests/mkgif.py [outdir]     # default /tmp; the repo's are in demo/

GIF suits a MODE 4 screen: sixteen colours and a palette, which is what the
SAM has, so the nibbles are palette indices already and nothing is
quantised.

## The frames are timed the way a display would show them

This is the part worth keeping. A routine that syncs to the flyback cannot
show a frame for part of a display frame: whatever it costs, it is held for
the whole number of 50ths of a second it fits into. So each frame carries
the delay **its own measured T-state count earns**:

    TICK   = 20         ms, one display frame on a 50 Hz SAM
    TFRAME = 120000     T-states of a 6 MHz Z80 in one of those
    held(ts) = [TICK * max(1, ceil(t / TFRAME)) for t in ts]

which is why the GIFs judder, and why their rates are lower than the mean
frame cost suggests:

| | frames held | rate |
|---|---|---|
| `lit_cube.gif` | 333 at 20 ms, 167 at 40 ms | 37.5 Hz, not 50 |
| `room.gif` | 165 at 40 ms, 85 at 60 ms | 21.4 Hz, not 25 |
| `maze.gif` | 42 at 120 ms, 58 at 140 ms | 7.6 Hz |
| `maze96.gif` | 132 at 80 ms, 18 at 100 ms | 12.1 Hz |
| `mazewide.gif` | 150 at 80 ms | 12.5 Hz |

An earlier version used one fixed delay taken from the mean cost. That
flattered every demo, because in each of them the worst poses overrun. If
you add a demo, sum the T-states of **everything that would run in a frame**
— the physics as well as the renderer — and pass them through `held`.

## Reading it back

`check_gif` compares against a decode of the written file. Two Pillow
behaviours to know:

- It **merges runs of identical frames** and adds their delays together.
- It **renumbers the palette**.

So both sides are converted to RGB and spread back out into display frames
before comparing, and a length mismatch counts as an error. A stray
difference shows up as a nonzero "wrong" count in the report.

## Why Pillow and not a hand-rolled encoder

The first version wrote its own LZW and was not spec-compliant, so every
GIF came out blank — and the round-trip check passed, because the encoder
and the decoder shared the same misreading of the width rule (the code
width increases when the next code equals `(1 << width) - 1`, not after).
**A check written against your own implementation checks nothing.** Pillow
writes the file; the read-back is Pillow's decoder against arrays that
never went through the writer, which at least closes the loop through a
different piece of code.

The uploads that failed with a 400 were the server rejecting corrupt
images, not a transport problem.

## Adding a demo

Write a function that builds a `Bench`, drives the routine frame by frame,
collects `(frame_array, t_states)`, and calls `write_gif` / `check_gif` /
`report`. `unpack` turns a MODE 4 buffer into one byte a pixel; `BUF` maps
a buffer page byte to its address. Palettes are 16 RGB triples; the demos
each have their own, since MODE 4 has no fixed one.

    pip install pillow numpy z80
