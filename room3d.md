# room3d.z80s — design notes

A first-person renderer for a convex room, 256×144 letterboxed into MODE 4,
double buffered, at 25 Hz in most views. No rays: the walls are drawn as
screen-space trapezoids.

Verified byte-for-byte against `tests/room.py` over the 256 camera
positions of `tests/test_room3d.py`.

## Interface

| symbol | |
|---|---|
| `r3d_init` | black both buffers, including the letterbox bars, once |
| `r3d_frame` | draw the room from `(r3d_cx, r3d_cz, r3d_ca)` and flip |
| `r3d_nw`, `r3d_rx`, `r3d_rc` | the room: wall count, vertex pairs, colour ramp bases |
| `r3d_cx`, `r3d_cz` | camera position, signed 16-bit world units |
| `r3d_ca` | heading, 0..255 |
| `R3D_NEAR` | near plane, 32 world units |

## Why not rays

A vertical strip touches one byte per scanline, and the fastest a byte can
be written that way is about 20 T-states — against 5.5 for a run along a
row written with `PUSH`. The viewport is 18,432 bytes, so **column order
costs 368,000 T-states a frame before a single ray is cast, and row order
101,000.** That number decided the whole design. (`wolf3d.z80s` is the
other side of the same argument: a texture forces column order, and there
the job becomes making a column cheap. Read both notes together.)

In a convex room every wall projects to a trapezoid and the walls tile the
view exactly — no gaps, no overlap, no sorting, no overdraw — so the
picture is the one the rays would have produced.

## The mechanism

**h is affine in screen x.** 1/z is affine across a plane and the wall half
height h is proportional to 1/z, so a wall's silhouette is a straight line
in screen space. That is what makes the trapezoid raster legal, and it is
also what lets a wall running off the side of the screen be clamped by
*interpolating h* rather than re-projecting.

**One accumulator a strip.** At height level j the wall covers a contiguous
c columns of its run, taken from whichever end is nearer:

    inc = n*256 / |hl - hr| ,  c(j) = min(acc >> 8, n) ,  acc += inc

**Two scanlines a step.** j runs 71 down to 0 and each step draws scanline
71−j and scanline 72+j: the viewport is symmetric about the horizon, so the
two share a split and differ only in whether the remainder is ceiling or
floor. Halves the edge walking.

**Everything is filled through runs of `PUSH BC`** entered n from the end,
two bytes every 11 T-states. Three things keep a run near the cost of its
pushes:

- What follows a run is the code that would have been jumped back to, so a
  run ends by *falling into* it and never pays for a return.
- An empty run — two in five of them — enters at the far end and costs
  nothing beyond its dispatch.
- There are two right-hand runs, 128 bytes apart in the same page. Which
  one a strip is sent to encodes whether its split fell inside a byte pair,
  so the rasteriser needs no test for it; the mixed-pair run falls into
  `r3d_roM`, which pushes one pair carrying a colour each side, and then
  into `r3d_roB` with the plain run.

**Wall boundaries snap to even byte columns** so every run is a whole
number of pairs, and the mixed pair keeps full two-pixel resolution at the
join.

**Rows above and below the sloped edge don't move the split** — five in six
of them — and are filled by `r3d_prep` without running the accumulator at
all.

**The raster loop derives its pointers from SP** rather than keeping them:
`LD HL,(r3d_k1) : OR A : SBC HL,SP : LD SP,HL`, with `k1 = 2*base +
192*128` and `k2 = k1 + 128`.

**Walls off the side are thrown out before projection**, on the signs of
vx−vz and vx+vz at both ends — a tenth of the cost of finding the same
thing out afterwards.

## Invariants

- **The room must be convex and the camera inside it.** Nothing checks.
- World coordinates should stay inside about ±2000 units.
- Walls come out of the room in winding order, which is a *rotation* of
  their order on screen; `r3d_rank` counts how many strips end to the left
  of each and fixes it. Strips must be emitted right to left because the
  fill runs down the stack.
- `r3d_pushes` is `ALIGN 256`: 64 `PUSH BC`, `JP r3d_roB`, padding to +128,
  64 more `PUSH BC`, then `r3d_roM` inline. `r3d_pushb` is a second aligned
  page. The alignment, the counts and the entry arithmetic are one
  mechanism.
- The letterbox bars are blacked once by `r3d_init` and never touched.
- `r3d_prep` builds its table with the writes running *down* each entry,
  so the step on to the next row is the stride plus however far they ran —
  `stride + 1` as the code stands, and the comment at `r3d_stride`'s use is
  the thing to read before touching it. Getting that step wrong corrupts
  every row, which is how it was found.

## What it costs

Over 256 camera positions, T-states:

    r3d_frame     min 184,714   mean 237,161   max 307,720

A 6 MHz SAM has 240,000 between 25 Hz frames. The cost is about 150,000
fixed plus 40,000 a visible wall:

| walls in view | frames | mean |
|---|---|---|
| one | 23 | 187,270 |
| two | 161 | 229,674 |
| three | 70 | 268,769 |
| four | 2 | 307,311 |

So two walls or fewer holds 25 Hz — 72% of the demo — and a corner with
three or four runs at 19 to 22. Held to the flyback that rounds to whole
50ths: over `demo/room.gif`, 165 frames at 40 ms and 85 at 60 ms, 21.4 Hz.

Mean frame: push run 103,825 (44%), rowout 44,510 (19%), raster 20,874
(9%), divide 19,718 (8%), prep 15,544 (7%), xform 9,846 (4%), onewall 9,176
(4%), qsmul8 7,578 (3%).

5,632 bytes, 2,888 of it code.

## The optimisation pass: 291,953 → 237,161

What worked, in order of size: dispatching each run by its entry byte
(60 T-states against the ~117 the pushing itself costs, so the dispatch
stopped being the thing); the `r3d_prep` constant-region fast path (82% of
prep was sitting in regions where the split does not move); the frustum
reject before projection.

**What did not work, measured:**

- *Merging adjacent runs of the same colour.* Worthless — the runs are
  already entered n from the end, so a merged run saves one dispatch and
  costs the test that found it.
- *Skipping empty runs explicitly.* A wash, **and it was wrong**: a run's
  first colour comes from the register the previous run left it in, so
  skipping one silently corrupts the mixed pair. Reverted.

## If you pick this up

The push run is 18,432 bytes at 5.5 T-states each and cannot be beaten; at
44% of the frame it is the floor, not the problem. The two things left:

1. **The restoring divide, 19,718 T-states.** A normalised reciprocal would
   take most of that.
2. **The fixed geometry cost** — divide, xform, onewall, qsmul8, some
   46,000 T-states — is what keeps three-wall views over budget. It does
   not scale with the walls in view, so it is the whole difference between
   25 Hz always and 25 Hz usually.

## A trap for the model

The Z80 clips against the near plane as a fraction then a multiply; a model
that divides the product instead disagrees in the last bit. `tests/room.py`
computes `t = ((-d0) << 16) // (d1 - d0)` and then `>> 16` to match. If you
change one side, change the other.

    python3 tests/test_room3d.py
