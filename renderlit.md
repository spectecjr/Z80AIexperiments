# renderlit.z80s — design notes

`render.z80s` with face lighting: eight shades a face, and a visibility
test rebuilt around the real face normals, for about 4% more per frame.
Only the differences are described here — the rasteriser, the buffers, the
dirty-rectangle erase and the span fill are identical, and `render.md`
covers them.

Verified byte-for-byte against `tests/rasterlit.py` over the 400 demo
frames of `tests/test_renderlit.py`.

## Interface

| symbol | |
|---|---|
| `rndl_init` | blank both buffers **and build the shade ramp** |
| `rndl_frame` | erase, light, draw, flip |
| `rndl_light` | the whole lighting and visibility pass, 8,829 T-states |
| `rndl_lite` | light direction in view space, 1.7 signed — `-52,52,-104` |
| `rndl_base` | where each face's ramp starts in the palette: `0,0,8,8,0,8` |
| `RNDL_LEVELS` | 8 — level 0 black, level 7 full |
| `RNDL_AMBIENT` | 2 — the level a face gets with the light behind it |

## The one idea

**A cube's face normals are the columns of its rotation matrix.** So the
six dot products `N·w`, for any single vector `w`, are the three components
of `Mᵀw` and their negations. One matrix-transpose-times-vector gives all
six faces at once, for 3,050 T-states. `rndl_light` does exactly two of
them a frame:

    w = T >> 8   (the translation, one signed byte an axis)  ->  visibility
    w = L        (the light)                                 ->  shade

**Visibility, exactly, under perspective.** A face is towards the viewer
iff `N·(T + S·N) < 0`, where `T` is the translation and `S` the half-size —
and since the normals are unit, that is just `N·T + S < 0`. The screen-
space cross product `render.z80s` uses would do, but the normals are being
computed for the lighting anyway, so this comes almost free, and it is the
exact perspective test rather than the orthographic one.

**The ramp.** Built once at init:

    level = AMBIENT + (max(shade, 0) * (LEVELS - AMBIENT)) >> 7

so a face lit straight on gets level 7 and one facing away gets 2, never 0
— a black face on a black background loses its silhouette.

## Invariants

- `rndl_base[face] + RNDL_LEVELS - 1` must stay inside the palette; with
  bases 0 and 8 and 8 levels, the two ramps exactly fill 0..15.
- `rndl_lite` is 1.7 fixed point and should be a unit vector; the shade
  scaling assumes `|N·L| <= 128`.
- Everything `render.md` lists — mask polarity, sliver skipping, the
  `PUSH` run's alignment — applies here unchanged.

## What it costs

|  | min | mean | max |
|---|---|---|---|
| `rndl_frame` | 43,588 | 81,072 | 107,681 |

`rndl_light` is 8,829 of that; one `Mᵀw` is 3,050; `rndl_init` is 37,583
once.

With `democube`'s 21,782 in front of it a mean frame is 102,854 T-states,
86% of the 120,000 a 6 MHz SAM has between 50 Hz interrupts. Over the 500 frames of
`demo/lit_cube.gif`, 333 are held for one display frame and 167 for two —
37.5 Hz, not 50. Raw T-states throughout; real SAM screen contention is on
top of all of it.

2,048 bytes: 1,280 code and small tables, 256 for the shade ramp, 512 for
the two scanline arrays.

## The rasteriser, after the second look

The first version of these notes said the rasteriser was close to its
floor. It was not. Measuring a single quad of a known size gave

| | a face | a scanline |
|---|---|---|
| before | 3,040 | 798.5 |
| **now** | **2,274** | **713.5** |

and none of it changed a pixel — every one of the six demos that draw
through renderlit still matches its model byte for byte. What did it:

1. **The span's end masks are immediates, not arithmetic.** Which half of
   a byte an end covers is decided by nothing but the parity of x, so each
   end branches on its own bit 0 rather than building a keep-mask out of
   `RRA` and `SBC A,A` — 23 T-states an end. The ends that turn out to be
   whole bytes become a plain store. Worth about 26 T-states a span, and 68
   on the one-byte ones. **The spans are short**: over prism's 256 frames
   the mean is 5.9 bytes and a tenth are one byte, so 103 T-states of
   filling sat behind 187 of setup.
2. **The screen pointer moved into the other register set**, and the
   scanline arrays are read in the main one. Reading them there is 26
   T-states where fetching them across the sets was 55, and it leaves the
   span `B` to itself, so the `PUSH BC`/`POP BC` that guarded the call went
   too.
3. **The span is written out rather than called.** It had one caller, and a
   `CALL` and a `RET` around 160 T-states of work is 17 for nothing.
4. **The edge walk's branch is the other way round.** A scanline that moves
   x along at all is the exception on a steep edge, so the test now falls
   through when there is nothing to do: 39 T-states a scanline rather than
   44, and sideways travel costs 24 a pixel rather than 27.
5. **The gather and the six-face dispatch lost their loops.** Four corners
   is few enough to write out (91 T-states a point against 149), and the
   face index that used to live in memory - read, bumped and written back,
   30 T-states a face - is now two walked pointers.

What it bought, at the demos that use it: prism 493,506 → 457,869 T-states
a frame, prismpre 245,608 → 210,693 (24.4 Hz → 28.5), cubes 449,675 →
419,478. Both prisms then went further by skipping `rndl_setface` and
`rndl_six` altogether and calling `rndl_quad` for the faces they actually
draw — 446,602 and 204,625 (**29.3 Hz**). `rndl_six` is still there for
`cubes` and `democube`, which want the whole six-face pass.

**What is left is the span setup**, ~160 T-states of it a scanline against
17.5 a byte of actual filling, and the byte addresses and end masks inside
it. `polyfast.md` is the measured account of one attempt to go further, and
of why it did not.

## The cheap case, if you want the T-states back

A light fixed on an axis **in view space** — a headlight at (0,0,−1) —
makes `MᵀL` a row of the matrix negated: three byte copies instead of
3,050 T-states, and the lighting costs about 700 T-states a frame over the
unlit renderer. The light then turns with the camera, which for a single
spinning object is often what you wanted anyway.

    python3 tests/test_renderlit.py
