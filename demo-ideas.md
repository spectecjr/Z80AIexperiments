# What to build next — candidate demo routines

A shortlist for a future session, with each idea costed against what this
repo has actually measured rather than against intuition. Items 1 to 4 and
5 and 7 are built; the rest are not. Where a number is an estimate it says so; every number that is
not marked as an estimate was measured on the emulator and is quoted in one
of the `.md` notes beside the routine it came from.

## The cost model to judge against

A 6 MHz Z80 has **120,000 T-states between 50 Hz frames**, 240,000 at 25 Hz.
MODE 4 is 256×192 in 16 colours, two pixels a byte, 128 bytes a line —
**24,576 bytes a screen**.

| getting a byte onto the screen | T-states | where measured |
|---|---|---|
| constant run along a row, `PUSH` | 5.5 | `room3d`, `wolf3d` prefill |
| the same, including all overhead | 5.8 | `wolf3d` prefill |
| flat column, no texture | 18.4 | `wolf3d` probe |
| textured column, two pixels wide | 22.8 | `wolf3d` |
| textured column, four pixels wide | 14.5 | `wolf3d` |
| an arbitrary computed byte | **109.7** | `roto` — and the estimate here was 30–40, which was wrong by three times |

Two consequences worth keeping in front of you:

- **A full screen of constant runs is 135,000 T-states.** More than a 50 Hz
  frame. Anything that repaints all 24K every frame is a 25 Hz routine at
  best, whatever it is painting.
- **A per-pixel computed effect gets about 2,200 bytes a frame at 25 Hz.**
  Measured, not estimated: `roto` does 4,096 of them at 13.4 Hz. The whole
  screen computed per byte would be about 2 Hz.

So the effects that fly here are the ones made of *runs*, and the ones that
crawl are the ones made of *pixels*. Every entry below is really a question
about which of those it is.

---

## 1. Space Harrier checkerboard floor  — **BUILT, three ways**

| | phase | width | T-states | |
|---|---|---|---|---|
| `chequer.z80s` | 4 px | 4 px | 92,404 | 50 Hz |
| `chequer2.z80s` | **1 px** | 4 px | 104,301 | 50 Hz |
| `chequer3.z80s` | **1 px** | **1 px** | 110,556 | 50 Hz |
| `harrier.z80s` | 1 px | 1 px | 221,420 | 25 Hz |

`chequer3` is the one to use: it draws harrier's screen, bit for bit, in
half the time, and still fits a 50 Hz frame. It costs 12K of compiled run,
which is the only reason to reach for one of the others. See `chequer.md`,
`chequer2.md`, `chequer3.md` and `harrier.md`. What follows is the original
note.

An infinite checkerboard plane, fixed camera height, scrolling horizontally
and vertically. Fixed Y-height for now; a moving camera height is a later
change and only affects the tables.

**The trick that makes it cheap: the depth alternation is the palette, not
the pixels.** With the camera height fixed, each scanline is one fixed
depth, so the checker's row parity is constant along a scanline. Draw the
whole floor in two logical colour indices and flip what those two indices
*mean* per scanline, and the depth stripes cost a couple of `OUT`s at a
scanline boundary instead of a repaint.

That leaves the pixels encoding only the vertical lines of the
checkerboard, which gives the floor two properties worth stating plainly:

- **Vertical (forward) scrolling costs nothing in pixels at all.** It only
  moves the scanlines at which the palette flips. The vertical lines of the
  checkerboard do not move with it.
- **Horizontal scrolling is the only thing that touches pixels,** and it is
  a phase per scanline: `φ(y) += k(y)` each frame, with `k(y)` a fixed
  table — one add and one compare-and-subtract a scanline. The fact that
  `k` differs per scanline *is* the parallax.

**The fill.** A scanline is a square wave of period `p(y)` bytes. Compile
one run of 64 `PUSH`es per distinct period, alternating `PUSH BC` / `PUSH
DE` with that period, and enter it n from the end for the phase — the same
mechanism as `room3d`'s runs and `wolf3d`'s scalers, generated at init.
One dispatch a scanline, not one per checker square, which is what stops
the run count exploding near the horizon. About 30 distinct periods at ~66
bytes each is ~2K of generated code.

Estimated: 96 floor scanlines × (128 bytes at 5.5 T + ~90 of phase and
dispatch) ≈ **76,000 T-states**, inside a 50 Hz frame with room for a sky
and sprites. To be measured, not believed.

**Open questions**

- Phase resolution. Entering the run n pushes from the end shifts by two
  bytes — four pixels. One byte (two pixels) comes free by starting SP a
  byte lower, at the cost of an overhang to park somewhere; one *pixel*
  needs a mixed pair at each boundary, which is `room3d`'s trick but costs
  a register load per boundary.
- Near the horizon the period goes below a pixel. Stop the checkerboard a
  few scanlines short and let a single blended colour meet the sky — which
  the palette gives free.
- **The palette half cannot be verified by the test bench.** The emulator
  is a plain Z80 core with memory and no SAM ASIC: no display, no line
  interrupt, no CLUT. The pixel half verifies as usual against a model; the
  raster timing can only be reasoned about here and confirmed on SimCoupe
  or hardware. `tests/mkgif.py` can still show the intended picture — give
  the GIF writer a per-scanline palette and it renders what the flips would
  produce.
- Hardware detail to confirm against the manual before building: the CLUT
  is written through port 248 with the entry index in the high address
  byte, and the line interrupt is programmed through port 249.

**Reuses:** `room3d`'s compiled `PUSH` runs entered n from the end and its
mixed-pair fill; `wolf3d`'s init-time code generator.

---

## 2. The twister — **BUILT**

`twist.z80s`, 105,690 T-states, 50 Hz. The estimate below was 106,000,
which is the closest any estimate in this file came. See `twist.md`.

A rotating ribbon of square cross-section, drawn as horizontal spans, one
or two visible faces shaded differently.

The pick of the classics for this machine, because it is made entirely of
horizontal constant runs — the one thing the hardware is good at. Per
scanline: angle = base + y·delta, four corner x's from the sine table
(~80–100 T), at most two faces visible, so three boundaries and three or
four runs. A 64-byte-wide band over 192 scanlines is 12,288 bytes at 5.5 T
= 68,000, plus ~200 T a scanline of setup = 38,000: **~106,000 T-states
estimated**, inside a 50 Hz frame.

It would be the first thing in the repo to run full screen height at 50 Hz,
and it needs no erase — every byte in the band is written exactly once.

**Reuses:** the `PUSH` runs; `renderlit`'s shade ramps, so faces can darken
as they turn. The face split at two-pixel resolution is `room3d`'s
mixed-pair problem exactly.

---

## 3. Rotozoomer — **BUILT**

`roto.z80s`, 449,272 T-states for a 128x64 window, 13.4 Hz, and it
measured the number this file had wrong. See `roto.md`.

A rotating, zooming texture. The honest stress test, and the reason to
build it is that **it would measure the one number missing from the table
above**: what an arbitrary computed byte costs.

The inner loop is two fixed-point adds and a texel fetch per byte, which
lands somewhere near 40 T-states however it is arranged — no run structure
to exploit, because consecutive bytes differ. That is about 6,000 bytes a
frame at 25 Hz: a 128×96 window, or the whole screen at ~6 Hz.

Worth doing for the measurement even if the picture stays small. The
plausible tricks to try: a 32×32 texture page-aligned so the fetch is one
`LD A,(DE)` off a row table; and whether the fractional adds can be folded
into a single `ADD HL,DE` with a texture layout that makes the carry
harmless.

---

## 4. Voxel landscape — **BUILT**

`vox.z80s`, 313,302 T-states a frame, 19.2 Hz, bit exact over 16 camera
positions. The estimate below said 17 Hz and the three decisions it
records are the ones that got it there. See `vox.md`.

What follows is the note written while modelling it.

`tests/vox.py` is the model and it renders correctly (a landscape, a
horizon buffer, no overdraw). What stopped it being written in assembly
this session was working out what a *sample* costs, and it is dearer than
this entry assumed:

    x += dx, y += dy          60 T-states, two 16-bit adds
    map address from x and y  41, with the map 256 bytes and page aligned
    height to screen row      11, one table lookup
    compare with the horizon  ~15
    fill, when it rises       ~15 a byte, going upwards

which is about 150 T-states a sample before anything is drawn. At 64
columns of four pixels and 16 steps out that is 154,000, plus 12,288 bytes
of column at ~15 T each - call it 340,000, or 17 Hz. Viable, and worth
building, but not the free lunch this entry implied.

The three decisions that make the sample as cheap as that, all found while
modelling and all worth keeping:

- **A 16x16 map, page aligned**, so a cell's address is one byte - exactly
  `roto`'s texel trick. The world tiles every 16 cells, which at three
  cells a step and 16 steps repeats three times across the view. A 32x32
  map costs another six instructions a sample.
- **y in 4.12**, so its row is already in the top nibble of its high byte
  and needs no shifting - also `roto`'s.
- **Sixteen height levels and sixteen steps**, so the height-to-row table
  is indexed by `(h & 0xF0) | z` - the height needs no shift at all, and
  the table is one page.

The original entry follows.

## 4. Voxel landscape

Comanche-style heightmap, front to back with one horizon byte a column.

The best *fit* of anything on this list, and it reuses `wolf3d` wholesale.
Its cost model is the favourable one: front-to-back with a per-column
horizon means **every screen byte is written exactly once and there is no
overdraw at all** — unlike `wolf3d`, which prefills and paints over 78% of
it. A 64×64 heightmap plus colourmap is 8K, which fits in the 16K that is
not screen; 128×128 would not.

More game-tech than demoscene, which is the only reason it is fourth.

### 5. Room Maze - can we make the room render an actual simple maze?  — **BUILT**

`portal.z80s`, 400,481 T-states a frame, 15 Hz. room3d's renderer driven
recursively: the maze is cut into nine convex cells, each drawn with the
window narrowed to the columns the door into it lands between. No sorting,
no depth buffer, still no overdraw. See `portal.md` - especially the note
on where the camera may stand, which is the near plane's doing.

What follows is the original note.

Same as the existing room kind of implementation, but now it actually renders a more complex room.

### 6. Lit 3D Convex Shapes  — **BUILT, on a provisional shape**

`prism.z80s`, 453,848 T-states a frame, 13.2 Hz. An extruded quad has
exactly a cube's shape - eight vertices, six quad faces - so a logo cut into
convex quads is a handful of cubes that are not cubes, and renderlit draws
them unchanged. The sigma and the triangle are built from the description
below rather than from the artwork; swapping the shape is a data change.
See `prism.md`.

What follows is the original note.

It'd be great if we could take the 3D Lit Cube renderer and see if we could use it to render the
Entropy demo group logo. This is a simplified serif-Sigma made out of 45 degree angles. with a triangle
with a hole cut out of the middle, entering the space to the left of the sigma. I'll provide an
image later. The triangle is red, the sigma is white, and the entire form should be extruded by some
amount so that it's not flat. The size of the object can be limited to 1/4 of the screen maximum in scale

### 7. Bouncing cubes  — **BUILT**

`cubes.z80s`, 444,593 T-states a frame, 13.5 Hz. Four lit cubes with
gravity, bouncing off the walls and off each other with integer physics and
no multiplication, in a room drawn as a wire frame. See `cubes.md` - the
room's far wall is where 16 bits ran out, and the line drawer is worth
130,000 T-states of the frame.

What follows is the original note.

We can limit the scale of the cubes so that they only take up 1/8th of the screen maximum. Then we
could render multiple cubes, and have them bounce with simple (integer math, no multiplication) physics
and gravity against the walls (and possibly each other). We should also render the outline of the room
they're bouncing around in, around the edge of the screen, and behind them for the other edges.

### 8. Copper bars and a raster split  — *free, and the cheapest thing here*

Nothing is drawn at all. The palette is rewritten a few times a scanline,
as `chequer.z80s` already does for its depth stripes, and the bars are
whatever the CLUT says. Cost is the copper list, not the picture: a bar
that moves is two palette writes a scanline, and 192 scanlines of that is
a few thousand T-states.

**Why it is worth doing anyway:** every routine in this repo spends 40-70%
of its frame on the span fill, and this one spends none. It is the natural
thing to put *behind* something else - a twister, a scroller, the cubes -
because it costs nothing that the foreground wanted.

### 9. Starfield  — *estimated 20,000 T-states for 500 stars, 50 Hz*

Each star is one pixel: erase where it was, move it, plot it. Measured
neighbours: `cubes.z80s`'s line drawer plots a pixel with a known address
for 25 T-states, and finds an unknown one for 130. A star costs the second
kind twice (erase and plot) plus a 16-bit add, so about 300 - call it 500
stars in 150,000, or 200 stars in 60,000.

Perspective is one divide a star, or a table of 256 reciprocals as
`transform3d.z80s` already has. **The interesting version is 3D**: z
decreasing, x/z and y/z projected, which is the same arithmetic `t3d_run`
does eight times a cube.

### 10. Fire, at quarter resolution  — *estimated 90,000 T-states, 50 Hz*

The classic: each row is the average of a few pixels of the row below,
minus a little, with noise seeded along the bottom. Per byte it is three
reads, an add, a shift and a write - about 30 T-states with the addresses
walked rather than computed.

**Full screen it is 24,576 bytes and hopeless** (740,000). At 128x96, one
MODE 4 pixel doubled both ways, it is 3,072 source bytes and 90,000
T-states, and the doubling out to the screen is 5.5 a byte with `PUSH`.
That is the whole argument for quarter resolution in one line, and it
applies to water ripple and plasma equally.

### 11. Vector balls  — *estimated 120,000 T-states for 24 balls, 25 Hz*

A sprite per ball, sorted back to front, scaled by z into two or three
sizes rather than continuously. A 16x16 sprite is 128 bytes; blitting one
with a mask is about 15 T-states a byte, so 2,000 a ball, plus the erase
which the dirty-box trick in `render.z80s` already solves. 24 balls in a
rotating cube or torus formation is 50,000 of blit and the transform of 24
points on top.

**This is the one that reuses the most of what is here** - `transform3d`
projects the points, `cubes.z80s` sorts them and keeps a dirty box each,
and nothing new has to be invented.

### 12. A one bit film  — *estimated 8 Hz full screen, 25 Hz at a quarter*

Run-length decode a stream into the frame buffer. A run of a colour is
`PUSH` at 5.5 T-states a byte, and the decoder between runs is about 40, so
a frame is 135,000 plus 40 a run. Full screen at 300 runs a frame is
147,000 - about 8 Hz once the erase is counted, which is what makes it a
quarter resolution idea too.

The reason to build it is not the film: it is that **a compiled run bank
is the same shape as a decoded run**, and the two could share a fill.

---

## Also considered, and why they rank lower

- **Tunnel** — same cost class as the rotozoomer (a computed byte with two
  table lookups), without the rotozoomer's virtue of measuring a clean
  number. Do the rotozoomer first and the tunnel becomes a variation.
- **Plasma** — cheap only if you exploit separability and the palette, at
  which point it is a palette effect rather than a routine. `c(x,y) =
  A[x+t1] + B[y+t2]` makes each row a shifted slice of one table, so the
  screen becomes 24K of *copying* at ~13 T a byte — 320,000 T-states, worse
  than computing a quarter of it.
- **Fire** — needs a neighbourhood average per byte, so ~50 T a byte and
  nibble unpacking on top. A small strip only.
- **Shadebobs** — additive blobs through a saturating add table into a
  16-level ramp. Genuinely cheap (a 16×16 blob is 128 bytes at ~25 T, so
  sixteen of them plus erase is well inside 50 Hz) and a good use of the
  palette. Small, but the cheapest impressive thing on the list.
- **Copper bars and palette cycling** — nearly free on this hardware, and
  the right backdrop for any of the above rather than a routine in itself.
  Same caveat as the checkerboard: not verifiable by this test bench.

---

## The house rules, for whoever picks this up

Every routine in this repo was built the same way and it is worth keeping:

1. Write the model in Python first (`tests/*.py`), and make it the same
   arithmetic — not a floating-point idealisation of it.
2. Verify the Z80 against the model **bit-exactly**, over enough poses to
   catch the corner cases, before optimising anything.
3. Measure with the emulator. Do not trust an estimate, including the
   estimates in this file — several of them will be wrong, and the ones in
   the finished headers are all measurements for that reason.
4. Record only measured numbers in the file headers, and mark estimates as
   estimates everywhere else.
