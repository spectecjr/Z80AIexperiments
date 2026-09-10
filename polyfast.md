# polyfast.z80s — design notes, and a measurement that says no

A convex quad rasteriser built to attack the one number that dominates
renderlit: **the scanline**. It works, it is verified byte-for-byte against
`tests/polyfast.py` over 300 quads, and **on faces the size this repo
actually draws it is 11% slower than the rasteriser it was meant to beat.**

That is the useful part. The numbers below say where a polygon fill's time
really goes on a Z80, and they are all measured.

## Where renderlit's time goes

Timing `rndl_six` on a single quad of a known size, on the emulated Z80:

| | T-states |
|---|---|
| a face, before any scanline | 3,040 |
| each scanline | 798.5 for a 40-pixel-wide span |
| of which actual filling | 17.5 a byte — 367 of that 798 |
| **overhead a scanline** | **431** |

and the overhead splits roughly into two edge walks (39 T-states a scanline
each, **plus 27 for every pixel of sideways travel**), 55 to read the two
scanline arrays back through `EXX` and a `PUSH`/`POP`, about 120 of span
setup and about 90 of loop. On the logo that travel term averages 55
T-states a scanline, and 46% of edges are shallower than 45°.

So: 128,000 T-states a frame of scanline overhead against 36,000 of filling.

## What polyfast does instead

No scanline arrays. Each side of the quad is a chain of edges walked as an
**8.8 fixed point DDA in a register pair** — a scanline is one `ADD HL,BC` a
side, eleven T-states, and the same eleven whatever the slope. The steps are
constant while both chains stay on the same edge, so they are patched into
the loop as immediates and a quad is drawn in one to three segments.

A step is `dx * 256 / dy`. Dividing costs 850 T-states, so `pf_init` builds
a 384-byte table of `65536 / dy` and an edge is two quarter-square
multiplies — 342 T-states. The price is a truncation under a 256th of a
pixel a scanline, so under a pixel over the tallest edge there can be.

## The measurement

| | a face | a scanline |
|---|---|---|
| renderlit | 3,040 | 798.5 |
| **polyfast** | **6,638** | **760.5** |

**They cross at 95 scanlines a face. prism's faces average 23.**

The design goal was met — the scanline did get cheaper, and it is now flat
in the slope, which is the part renderlit is worst at:

| a 40×32 quad | renderlit | polyfast |
|---|---|---|
| upright | 28,592 | 30,974 |
| slanted 32 | 30,576 | 30,968 |
| slanted 64 | 32,560 | **30,968** |

— but only by 38 T-states a scanline, and the DDA needs a step per edge
where Bresenham needs nothing at all. 3,598 T-states of extra setup buys 38
a scanline back. On a logo that is 13.3 faces and 301 scanlines a frame:
11,400 saved on scanlines against 47,900 spent on faces.

## Why the scanline only got 38 T-states cheaper

Because the edge walk was never the big term. Of renderlit's 431 T-states of
overhead, the two edge walks are 78 and the array fetch 55 — polyfast
removes 133 and spends 60 on its own DDA, 42 pushing and popping the two x
accumulators and the two fractions around the span (which trashes B, C, D
and E), and the rest on the same loop. **The other ~300 T-states a scanline
are the span setup and the loop itself, and they are the same in both.**

## What would have to change

1. **The span setup, not the edges.** ~300 T-states a scanline of the 431 is
   working out byte addresses, two end masks and loop bookkeeping for a span
   that then fills ten bytes at 17.5 each. That is the term to attack, in
   either rasteriser.
2. **Fewer spans.** Measured separately: merging the logo's coplanar front
   faces into one polygon each would remove 30 spans a frame of 120 — 25% —
   worth about 13,600 T-states, but it needs a rasteriser that can put more
   than one span on a scanline, and the crossing sort costs about what the
   merge saves.
3. **The fixed cost, if the DDA is to be kept.** 6,638 against 3,040: two
   multiplies an edge (1,048 a face), chain building (~800) and segment
   setup (~750). Halving those would move the crossing point to about 50
   scanlines a face — still above what a logo or a cube needs.

## Running it

    python3 tests/test_polyfast.py    # 300 quads against the model, and
                                      # the cost curve of both rasterisers
