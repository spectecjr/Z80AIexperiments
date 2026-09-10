# cubes.z80s — design notes

Four lit cubes bouncing in a room you can see: gravity, walls, each other,
and a wire frame around the box they are in. **444,593 T-states a frame,
13.5 Hz**, verified byte-for-byte against `tests/cubes.py` over 300 frames.

`democube.z80s` moves one cube and `renderlit.z80s` draws it; this does the
same for four, so most of the file is about what having four of something
costs rather than about drawing.

## The physics is integers, and there is no multiplication in it

    v.y -= G                    gravity, one add a frame
    p   += (v + f) >> 4         democube's step, the remainder kept
    wall:  p to the wall, and v = -v if it was heading out
    cube:  swap the two v's along the axis they overlap least in

Swapping is what two equal masses do in a head-on hit, and the axis of
least overlap is the one they met on. All of it is elastic, so the demo
runs for ever without either dying down or running away — `tests/cubes.py
--long` checks that over a million frames: no cube ever leaves the room and
no speed ever exceeds 2,300 of the 6,000 the fixed point allows.

**The wall holds the position as well as turning the velocity round.** That
is not decoration: a cube squeezed between a wall and another cube gets an
inward-pointing velocity handed to it every frame, and without the clamp it
burrows out of the room a step a frame for as long as the squeeze lasts.
That was measured at ten world units before it was fixed.

The cube-cube test is on the cubes' **unrotated** extent, 2S, not on their
bounding spheres. Four spheres of radius S√3 do not fit in this room with
any freedom left, and a corner that dips into a neighbour for a frame is
not what anybody is looking at.

## The room is where the sixteen bits ran out

The far wall is at z = 254 because of arithmetic, not taste. `transform3d`
adds up to `R * 128` of rotated corner onto the centre and the sum has to
stay inside a signed word, which caps the centre at 195 units of z at this
cube size. The other three dimensions follow from the viewport the front
face has to fill: at focal length 64 and a near plane of 100, a room 187
wide and 140 tall projects to 8..247 by 7..186.

**Its front face is the viewport, so the frame around the viewport is
painted once and never touched again** — the room's own walls keep the
cubes off it, and the erase widening to whole byte pairs cannot reach it
either. The other eight edges are drawn every frame, because a cube goes in
front of them and the erase takes them with it when it goes.

## Drawing four of something

- **The erase is four boxes, not their union.** Four cubes spread out have
  a union of nearly the whole screen, which at 5.5 T-states a byte would be
  135,000 on its own; four boxes of their own are 31,464.
- **Farthest first.** A bubble sort on z, and then each cube in turn gets
  democube's spin and multiply tables, `t3d_run`, `rndl_light` and
  `rndl_six`. Nothing is clipped and nothing is sorted within a cube —
  renderlit's per-face visibility still does that.
- **Each cube keeps its own dirty box**, copied out of renderlit's after
  `rndl_bbox`, because the erase two frames later has four to do.

renderlit grew three seams for this and nothing else: `rndl_six` (the
six-face loop without the erase, the box and the flip), `rndl_bstore` and
`rndl_erasebox` (the box and the erase, of any record rather than this
buffer's). Its own test still passes byte for byte, 37 T-states a frame
slower.

`democube`'s half-size became `DEMO_HALF`-overridable at the same time: the
cube size decides how much room the centre has before 16 bits overflow, and
34 buys 36 units of z where democube's 40 buys 17.

## What it costs

| | T-states | |
|---|---|---|
| `cb_draw` | 327,218 | 74% — four cubes of transform, light and faces |
| `cb_room` | 56,132 | 13% — eight edges, 624 pixels |
| `cb_erase` | 31,464 | 7% |
| `cb_phys` | 20,259 | 5% — four cubes and six pairs |
| `cb_order` | 4,734 | 1% |
| **`cb_frame`** | **min 374,586, mean 444,593, max 490,739** | 13.5 Hz |

Held to the flyback, `demo/cubes.gif` runs at 12.4 Hz.

**The line drawer was worth 130,000 T-states of that.** Written the obvious
way — work out the address of each pixel from its x and y — the room cost
178,000 T-states a frame, 285 a pixel. The edges come out of the table with
their major axis increasing, so the fast step is always forwards and the
address can be *walked*: along a row the nibble alternates and the byte
moves on every second pixel, and down a column it is 128 bytes a scanline
with the nibble standing still. 55 T-states a pixel, and the same picture.

## If you pick this up

1. **Three cubes would fit 25 Hz** — `cb_draw` is 82,000 a cube and almost
   all of it is renderlit's span fill, which is close to its floor. Four is
   a choice, not a limit.
2. **The room is drawn under the cubes and mostly painted over.** Clipping
   its eight edges to the four erase boxes would draw a third of the pixels
   for a comparable amount of arithmetic — worth measuring, not obviously
   worth doing.
3. **`cb_phys` is 5%** and could take collisions between all pairs of a
   dozen cubes before it mattered.

## Invariants

- The cube's half size, the room and the wall limits are one system: the
  room's front face has to project to the viewport, the centre limits are
  the room inset by the bounding sphere, and the far wall is where 16 bits
  run out. `tests/cubes.py` holds all of it; `mkcubesdata.py` emits it.
- Edges are stored with their major axis increasing. `cb_line` assumes it.
- The cubes must stay off the border, or the erase will eat it.
- `DEMO_HALF` and the model's `S` must agree.

    python3 tests/mkcubesdata.py    # regenerate the room and the cubes
    python3 tests/cubes.py --long   # a million frames of physics
    python3 tests/test_cubes.py     # verify the Z80 against it and time
