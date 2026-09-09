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
| `rndl_frame` | 47,953 | 90,439 | 121,003 |
| `render.z80s` unlit | 43,807 | 86,717 | 116,941 |

So lighting and the new visibility test together cost 3,722 T-states a
frame, 4.3%. `rndl_light` is 8,829 of that; one `Mᵀw` is 3,050;
`rndl_init` is 37,583 once.

With `democube`'s 21,782 in front of it a mean frame is 112,221 T-states,
94% of the 120,000 a 6 MHz SAM has between 50 Hz interrupts. **The worst
pose does not fit**: 121,003 for the renderer alone. Over the 500 frames of
`demo/lit_cube.gif`, 333 are held for one display frame and 167 for two —
37.5 Hz, not 50. Raw T-states throughout; real SAM screen contention is on
top of all of it.

2,048 bytes: 1,280 code and small tables, 256 for the shade ramp, 512 for
the two scanline arrays.

## The cheap case, if you want the T-states back

A light fixed on an axis **in view space** — a headlight at (0,0,−1) —
makes `MᵀL` a row of the matrix negated: three byte copies instead of
3,050 T-states, and the lighting costs about 700 T-states a frame over the
unlit renderer. The light then turns with the camera, which for a single
spinning object is often what you wanted anyway.

    python3 tests/test_renderlit.py
