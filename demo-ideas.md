# What to build next — candidate demo routines

A shortlist for a future session, with each idea costed against what this
repo has actually measured rather than against intuition. Items 1 to 4 and
5 and 7 are built; the rest are not. Where a number is an estimate it says so; every number that is
not marked as an estimate was measured on the emulator and is quoted in one
of the `.md` notes beside the routine it came from.

`tricks.md` explains the techniques behind these numbers — read it before
costing anything new.

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

## 1. Space Harrier checkerboard floor  — **BUILT, four ways**

| | phase | width | stripes | T-states | |
|---|---|---|---|---|---|
| `chequer.z80s` | 4 px | 4 px | palette | 92,335 | 50 Hz |
| `chequer2.z80s` | **1 px** | 4 px | palette | 104,232 | 50 Hz |
| `chequer3.z80s` | **1 px** | **1 px** | palette | 110,806 | 50 Hz |
| **`chequer4.z80s`** | **1 px** | **1 px** | **pixels** | **114,656** | **50 Hz** |
| `harrier.z80s` | 1 px | 1 px | palette | 221,451 | 25 Hz |
| `chequer5` | **1 px** | **1 px** | **pixels** | **129,183** | 25 Hz, board to the horizon |
| `chequer6` | **1 px** | **1 px** | **pixels** | **154,607** | 25 Hz, and a pilot in front of it |

`chequer4` is the one to use: it draws chequer3's screen — the GIFs come
out byte for byte identical — with the depth alternation in the pixels
rather than in a palette that has to be reprogrammed every frame, for 80
T-states a scanline. It shares chequer3's run bank unchanged, so the 12K is
not paid twice. See `chequer.md`, `chequer2.md`, `chequer3.md`,
`chequer4.md` and `harrier.md`.

**What the palette still does, and what it would take to stop.** The
distance fog is a per-scanline palette gradient in all five. Moving that
into the pixels too would leave the demo with no palette work at all, and
the numbers are friendlier than they look: the fog is only **6 distinct
colour pairs** over the 84 board rows (the SAM's palette quantises it),
the whole picture uses **14 of the 16 MODE 4 indices**, and a band drawing
its own two colours costs *nothing* at run time because chequer4 already
chooses a band's six values from a table. It needs 40 (value set, colour
pair) combinations — 1,280 bytes against chequer4's 416, where the low
block has 756 bytes spare — so it is a memory problem and a fifth routine,
not an edit.

**How far into the distance.** All of them stop the board at eight-pixel
squares and let a haze meet the sky, because below that a square is too
narrow to draw honestly. `chequer5` is chequer4's code with the viewport
opened all the way — squares down to one pixel, 95 scanlines, no haze — and
it lands at 129,183 T-states. That is a cliff rather than a slope:
chequer4's worst frame leaves 1,414 T-states of a 50 Hz frame, and the
cheapest step down the screen costs 2,350, so nothing in between fits
either. At 25 Hz it is 54% of the frame where harrier was 92%. See
`chequer5.md`, which also records what would have to come out of the
dispatch — 13,000 T-states, a fifth of it — to draw 95 scanlines at 50 Hz.

**A pilot in front of it.** `chequer6` puts a 32x96 person in a jetpack in
the middle of the screen for 25,528 T-states a frame, which is 64% of a
25 Hz frame all told. Three things make a sprite that size affordable: half
of him is above the board and so is drawn once into both buffers rather
than every frame; his silhouette is rounded out to whole bytes with his own
black outline, so no byte he draws needs a read-modify-write; and two
thirds of his rows repeat the one above, so 96 scanlines are 43 rows of
run-length stream. See `chequer6.md`.

**The camera in the GIFs.** All five demos now share `stroll()` in
`tests/mkgif.py`: a slide of two and a half squares either way taking
eight seconds, and a walk forwards of five squares a second. At the
bottom of the screen the board slides sideways at most **3 pixels a
frame, where it used to be 12** — the old swing was five and a half
squares in 3.8 seconds, which read as a lurch rather than a camera, and
did not divide into the length of the GIF either.

The swing also crosses square boundaries, which found a real bug: only the
low byte of `camx` reaches the phase, and the whole squares it drops are a
parity of their own, so the board jumped a whole square sideways every 256
world units. All five routines now fold that parity in with the depth's,
for nothing. See `chequer.md`.

What follows is the original note.

An infinite checkerboard plane, fixed camera height, scrolling horizontally
and vertically. Fixed Y-height for now; a moving camera height is a later
change and only affects the tables.

**The trick that makes it cheap: the depth alternation is the palette, not
the pixels.** (`chequer4.z80s` took it back out again — see above. It is
the same thing as a whole square of horizontal phase, and a phase is what
the pixels are already doing.) With the camera height fixed, each scanline is one fixed
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

`prism.z80s`, 446,602 T-states a frame, 13.4 Hz. An extruded quad has
exactly a cube's shape - eight vertices, six quad faces - so a logo cut into
convex quads is a handful of cubes that are not cubes, and renderlit draws
them unchanged. The sigma and the triangle are built from the description
below rather than from the artwork; swapping the shape is a data change.
See `prism.md`.

**Precomputed, it runs at 29.3 Hz.** `prismpre.z80s`, 204,625 T-states a
frame: the spin, the multiply tables, the 56 projected vertices, the 18
normals' shading and the back-to-front sort are all functions of the frame
number alone, so they go into a 144-byte-a-frame table and the frame becomes
renderlit's span fill and nothing else. The same frames to the byte. The
price is the loop: 9,216 bytes is 64 frames of free RAM, so the logo has to
come back to where it started in 64 frames and turns about three times
faster. See `prismpre.md`.

**A faster rasteriser was tried and measured down.** `polyfast.z80s` walks
each side of a quad as an 8.8 DDA in a register pair instead of Bresenham
into two scanline arrays, which makes a scanline cost the same whatever the
slope - 760 T-states against renderlit's 798, and flat where renderlit
climbs 27 a pixel of sideways travel. But a DDA needs a step per edge where
Bresenham needs none: 6,638 T-states a face against 3,040. The two cross at
95 scanlines a face and a logo's average 23, so it loses. What the numbers
say to attack instead is the span setup - about 300 of the 431 T-states a
scanline, for a span that then fills ten bytes at 17.5 each. See
`polyfast.md`.

**The artwork arrived, and it is traced rather than guessed.**
`entropylogo.png` went to vectors by boundary tracing and
Douglas-Peucker, and scores 3.0% against its own pixels. Nine convex
pieces rather than seven: `PRISM_SHAPE=entropy` builds it, 220,823
T-states a frame precomputed - 27.2 Hz - and 550,669 live. See
`entropylogo.md`.

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

### 9. Starfield  — **BUILT**

`stars.z80s`, 197,813 T-states a frame, 30.3 Hz, 192 stars — **and the
estimate below was wrong by three and a half times.** It said 300
T-states a star; the measurement says 1,030, of which only 332 is the two
multiplies and the rest is bookkeeping. 116 stars fit 50 Hz. See
`stars.md`.

What follows is the original note.

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

### 11. Vector balls  — **BUILT**

`balls.z80s`, 108,270 T-states a frame, **55.4 Hz**, twenty balls - and
the estimate below was about right for once. The trick that paid was not
in the note: putting the balls on a cube's corners and edge midpoints
makes every coordinate -S, 0 or +S, so the nine products (m*S)>>7 are
worked out once a frame and a ball's position is three signed adds. Nine
multiplies a frame rather than nine a ball, and transform3d is not needed
at all. See `balls.md`.

What follows is the original note.

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

---

## 15. Zarch / Virus polygonal landscape — **BUILT, flat**

`zarch.z80s` draws the flat half of it: a chequered plane under a camera
that turns, **208,206 T-states a frame, 25 Hz**, byte for byte against its
model over 96 cameras. See `zarch.md`. The costing that came first is below,
and it held up - the span count was the thing, and the span dispatch came
in at 33 T-states rather than 63 once the runs and the list shared a page.

The part nobody can guess at is what a flat-shaded span costs, so that part
was measured first: `spanfill.z80s`, **63.0 T-states a span and 5.51 a
byte**, verified bit for bit at six different span counts.

**The fill is not the problem.** 128 scanlines of full-width floor is
101,888 T-states — 42% of a 25 Hz frame — and `PUSH` means there is nothing
underneath that number.

**The span count is the problem.** A span in a real floor is not 63
T-states but about 127: 63 to draw, 39 to step the edge that produced it
(`renderlit`'s measured figure), and ~25 to turn two edge positions into an
entry byte (an estimate). Which gives, for 128 scanlines:

| grid, cells across | drawing | with edges and list building | of a 25 Hz frame |
|---|---|---|---|
| 4 | 134,144 | 166,912 | 70% |
| 6 | 150,272 | 199,424 | 83% |
| 8 | 166,400 | 231,936 | 97% |
| 10 | 182,528 | 264,448 | 110% |

**So the budget is about eight cells across, and that is the whole answer.**

**A flat rolling grid — no hills — looks like a 25 Hz routine.** Six to eight
cells across, 128 scanlines, and the geometry is nearly free: on a flat
plane every grid line is straight on screen, so only the *ends* of them need
projecting — about 36 vertices at ~300 T-states, not 144. Call it 200,000
T-states all in. It is a chequer floor with roll and a colour a cell, and
most of the machinery for it is already in `chequer3`.

*Built: 208,206, against an estimate of 200,000. It turned out to want no
vertices at all — a row is one depth, so each family of grid lines is an
arithmetic progression along it — but 56 rows rather than 128, because the
rows near the horizon are where the span count runs away.*

**Zarch proper — a heightfield with hills — is a `vox`-class routine, 13-17
Hz** (estimated). Three things change and all of them cost: every vertex
needs projecting rather than every line end (144 × ~300 = 43,000 T-states);
a bumpy cell is its own quad with its own two edges, so the edge count a
scanline roughly doubles; and there is overdraw, because quads no longer
tile the screen exactly. `vox.z80s` draws a heightmap at 19.2 Hz and `cubes`
draws four lit cubes at 14.3, which is the neighbourhood.

**What would decide it, if it gets built:**

- **A distance cutoff, not a uniform grid.** Zarch drew a grid whose far
  cells are a pixel across and still cost a span each. `harrier`'s haze is
  the answer: stop the mesh where a cell stops being worth 127 T-states and
  meet the sky with a graded band.
- **Pixel-exact boundaries or not.** Whole-`PUSH` spans put every polygon
  edge on a two-pixel grid, which on a rolling floor will shimmer. A mixed
  boundary byte is chequer3's trick and costs about 20 T-states a span
  (estimated) — worth it, and it is what takes 8 cells across down to 7.
- **Back to front, and no clipping.** Rows of the mesh drawn far first
  order themselves, which is the one part of this that is free.
