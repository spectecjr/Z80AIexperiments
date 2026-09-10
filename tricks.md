# tricks.md — what a Z80 is good at, and what it costs

Everything in this file was measured on the emulated Z80 by `tests/`, on the
routines named beside it. Where a number is an estimate it says so. The
machine is a 6 MHz SAM Coupé in MODE 4: 256×192, sixteen colours, **two
pixels a byte**, 128 bytes a scanline, 24,576 bytes a screen, **120,000
T-states between 50 Hz interrupts** and 240,000 between 25 Hz ones.

Read `costs.md` for what each demo came out at. This file is the other half:
*why*.

---

## 1. The one table that decides everything

**What a byte of picture costs, by how it is written.**

| | T-states a byte | where |
|---|---|---|
| a constant run, `PUSH` | **5.5** | `chequer`, `room3d`, `twist`, `zarch` |
| a copy, `LDI` unrolled | 16 † | `chequer6` |
| a span, `LD (HL),C` / `INC L` in pairs | 17.5 | `renderlit` |
| a flat column, no texture | 18.4 | `wolf3d` |
| a copy, `LDIR` | 21 † | — |
| a textured column, two pixels wide | 22.8 | `wolf3d` |
| an `LD (HL),0` erase loop | ~30 | what `render` replaced |
| a textured column, stepping by a fraction | 72.6 | what `wolf3d`'s scalers replaced |
| **an arbitrary computed byte** | **109.7** | `roto` |

† instruction timings, not a measured loop; everything else was timed.

Two consequences run through the whole repo:

**A run along a row is twenty times cheaper than a computed pixel.** So the
question for any renderer is not "how do I compute this pixel" but "what is
constant along a run, and how do I find the runs". `room3d` picks its entire
design off this: a vertical strip touches one byte a scanline at ~20
T-states, a horizontal run 5.5, and its 18,432-byte viewport is therefore
368,000 T-states in column order against 101,000 in row order. That number
decided the design before a line was written.

**A whole screen is 135,000 T-states even at the floor** — more than a 50 Hz
frame. Nothing that repaints everything can run at 50 Hz. Everything at 50 Hz
in this repo either draws a fraction of the screen (`renderlit`'s dirty
rectangle, `stars`' per-star erase) or draws all of it in runs and nothing
else (`chequer`, 92,335).

---

## 2. The stack pointer is the fastest thing on the chip

`PUSH BC` writes two bytes and moves the pointer in 11 T-states. Nothing
else on a Z80 writes memory at 5.5 T-states a byte. Every fill in this repo
that can be a `PUSH` is one.

**The costs.** `SP` is the return address register, so a `PUSH` fill runs
with `DI`, saves the caller's stack somewhere fixed, and puts it back at the
end. It also means no `CALL` may happen between — `zarch` writes return
addresses into the picture if the row loop's `CALL`s come before `SP` is put
back, which is a bug that took an afternoon.

**It writes downwards**, so a fill goes right to left and a screen fill goes
bottom to top. That is not free: whatever a run overruns on the left lands
in the row *above*, which is why `chequer` and `chequer3` draw the board
bottom upwards and repair only the topmost row's spill.

**It writes two bytes at a time**, so a span's ends quantise to a byte pair —
four pixels. `chequer` lives with that; `chequer3` and `room3d` do not (§4).

**One byte, when a pair is one too many.** `PUSH BC` / `INC SP` writes two
bytes and steps one, so the byte to the left is written and then overwritten
by the next span. Costs 17 T-states and buys two-pixel span ends.

**`SP` is also an addend.** `ADD HL,SP` is a sixteen-bit add like any
other, so a constant that has to be added every step can live in `SP` when
every register pair is taken: `roto` keeps `dv` there, because `ADD HL,SP`
is the only sixteen-bit add left once `HL`, `DE` and `BC` hold `u`, `v` and
`du`.

**And a pointer worth deriving from.** `room3d`'s raster loop keeps no
screen pointers at all — it subtracts `SP` from a constant and puts the
result back:

    LD HL,(r3d_k1) : OR A : SBC HL,SP : LD SP,HL

**`POP` is the fastest load on the chip**, ten T-states for two bytes.
`chequer3` and `chequer4` fill all six pushable registers — `BC`, `DE`,
`HL`, `IX`, `IY`, `AF` — straight off a table with six `POP`s a band, which
is also the only way to get a value into `F` at all.

---

## 3. Compile the picture into code

The dispatch around a fill is usually dearer than the fill. The answer is to
generate straight-line code, once, and jump into the middle of it.

**A run entered n from the end.** A run of 64 `PUSH BC` is 64 bytes, one
byte a `PUSH`, so "push n of them" is *jump to end − n*. One byte of
arithmetic, no loop, no counter, no test.

    r3d_pushes:  DUP 64 / PUSH BC / EDUP / JP r3d_roB

Used by `room3d`, `chequer`, `chequer2`, `chequer3`, `renderlit`, `zarch`
and `spanfill`. It is the single most reused idea in the repo.

**Bake the pattern in, not just the length.** `chequer`'s run alternates
`PUSH BC` and `PUSH DE` with the board's period baked into the opcodes, so a
scanline is *one* dispatch however many squares it holds — which is what
stops the cost exploding as the squares shrink towards the horizon.
`twist` goes further: a whole scanline, backdrop and both faces, is one
compiled run, and which register each `PUSH` names *is* the silhouette.

**Bake the awkward cases into separate entry points.** `room3d` has two
right-hand runs 128 bytes apart in the same page; which one a strip is sent
to encodes whether its end fell inside a byte pair, so the rasteriser needs
no test for it. `zarch` has two runs and the entry byte's bit 7 says which,
so the chequer's colour alternates for nothing.

**Generate at init when the shapes are data.** `wolf3d`'s scalers are one
unrolled run per wall height, mapping 32 texels onto n rows with the texture
step baked in: 72.6 T-states a byte becomes 22.8. `chequer`'s sixteen runs
cost 1,493,036 T-states to write, once, for 1,328 bytes.

**Or generate offline when they are big.** `chequer3`'s run bank is 8,722
bytes and comes out of `tests/mkchq3data.py`; `wolf3d`'s viewport tables
come out of `tests/mkwolfdata.py`. The rule that decides which: if the generator
needs floating point or a search, it goes in Python.

**Self-modify the operands.** An immediate is 7-10 T-states where a memory
read is 13-20 and a register is a register you have not got. `chequer3`
patches seven bytes into its row loop a band; `zarch` patches both families'
steps as `SUB n` / `SBC A,n` pairs, which is how the merge gets away with
using every register it has for something else.

---

## 4. Sub-byte edges without paying for them

Two pixels a byte means an edge that lands mid-byte needs a read, a mask and
a write — three times the work of a store. Three ways round it, in
increasing order of cleverness:

**Snap the edge to the byte.** `chequer6`'s pilot gives the odd pixel of a
partial byte to its own black outline, so **every byte the sprite draws is a
whole byte** and the whole thing is `LDIR`. The outline goes from one pixel
wide to two here and there, which is the cheapest possible answer.

**Precompute the mixed pair.** A boundary byte carrying one pixel of each
colour is just another value to push. `chequer3` keeps up to four of them in
`HL`, `AF`, `IX` and `IY` — an odd-width square needs all four, because its
boundaries walk through every offset inside a `PUSH` in turn — and gets
pixel-exact edges at `PUSH` speed. `room3d` has a mixed-pair run for the
same reason.

**Mask, but only at the two ends.** `render`'s span fill is whole bytes in
the middle and a read-modify-write at each end:

    LD A,(HL) : XOR C : AND E : XOR C : LD (HL),A

`renderlit`'s second pass turned the end masks into parity branches with
immediate masks and a plain store where an end turns out to be a whole
byte — 26 T-states a span, and 68 on the one-byte spans, which are a tenth
of them.

---

## 5. Registers: the ones you have, and the ones you can pretend to have

**Six things can be pushed**: `BC`, `DE`, `HL`, `AF`, `IX`, `IY`. `AF` is
the awkward one — `F` can only be loaded by `POP AF`, so once a colour lives
in `F` **nothing between that `POP` and the run may touch the flags**.
`EXX`, `LD SP,HL` and `INC SP` do not; `ADD HL,DE` does. That single fact
shapes `chequer3`'s entire row loop.

**`EXX` swaps `BC`, `DE` and `HL` together.** It does not swap `A`, `F`,
`IX` or `IY`. So:

- `A` is the one thing that survives a set switch, which is why `roto` and
  `vox` finish a whole address byte — both nibbles, OR'd — before coming
  back, and why `zarch`'s span player carries its list offset in `A`
  *through* a run of `PUSH`es.
- `EX AF,AF'` parks a byte and its flags in four T-states.
- A value needed on both sides has to be duplicated or passed in `A`.
- Loading a pointer *before* `EXX` puts it in the wrong set. That was a bug
  in `twist`: `SP` was set from garbage and the runs pushed over the low 8K.

**`IX` and `IY` cost 19 T-states an access.** Fine for setup, ruinous in a
loop: two thirds of `stars`' 1,030 T-states a star is index-register
bookkeeping, and `zarch`'s setup went from 300 T-states an iteration to 40
by getting `IX` out of the loop.

**When you run out, patch the code.** `zarch`'s per-row merge needs both
positions, the right-hand edge and a scratch — every register in the main
set — so the two steps are `SUB n` / `SBC A,n` immediates patched once a
row. Same speed as a register pair, no register.

**When you run out again, use the other `A`.** `chequer3` keeps the scanline
count and the row pointer in the alternate set and turns the loop round
there, because `A` and `F` are colours in the main one.

---

## 6. Tables, and the addressing that makes them free

**Page-align, and an index is one byte.** `roto`'s texture is 16×16 and
page-aligned, so a texel address is *one byte* — row in the top nibble,
column in the bottom. `vox`'s map is the same. `L` is the whole address
computation.

**Index by two things at once.** `vox`'s height-to-row and height-to-colour
tables are both indexed by `(h & 0xF0) | z`, so a sample's screen row and
its distance-faded colour are two lookups with no shifting at all — the fade
costs nothing.

**Put related tables in consecutive pages** and `INC H` or `INC D` walks
between them: `vox`'s two tables above its map, `twist`'s four consecutive
pages of run and shade.

**Lay a periodic table down twice** and reading off the end needs no wrap
test: `twist`'s 256 angles are stored twice so 192 scanlines can start
anywhere in them.

**Multiply by table.** `qsmul8` is the difference of quarter squares,
`a*b = floor((a+b)²/4) − floor((a−b)²/4)`, which is exact for integers
because `(a+b)` and `(a−b)` have the same parity: **131 T-states**, against
155 for the half-squares version, at the price of a 1,024-byte table across
four pages. Everything that needs a real multiply uses it — `stars`,
`balls`, `transform3d`, `polyfast`.

**Divide by table, or do not divide.** A 16÷8 division is **850 T-states**.
`transform3d`, `stars` and `balls` all avoid it with a reciprocal table:
`recip[z] = 256*64/z`, one lookup and one multiply. `polyfast` replaced its
`65535/dy` division with two `qsmul8`s — 850 down to 342 — and *still* lost
to the rasteriser it was attacking (§12).

**Replace the multiply with a lookup entirely.** `tab64` is MurmurHash3's
job done as a tabulation hash in the shape of a CRC —
`h = (h >> 8) XOR T[(h XOR byte) & 255]` — at 234 T-states a byte against
murmur3's ~90,000 for a short string. Twenty-five times quicker, because a
Z80 has no multiplier and does have a fast `LD A,(HL)`.

**Nine multiplies a frame, not nine an object.** `balls`' twenty balls sit
on a cube's corners and edge midpoints, so every coordinate is −S, 0 or +S,
so a rotated position is three signed *adds* off nine products worked out
once a frame. The nine are stored transposed so one coordinate's three
contributions are adjacent and the loop walks them with `INC HL`.

---

## 7. Fixed point: choose the scale so the answer is already in a register

This is the trick that keeps coming back, and it is worth stating on its
own: **pick the binary point so that the number you want to read out is a
whole register half.**

- `roto` and `vox` keep `y` in **4.12**, so its row is already the top
  nibble of its high byte. No shifting, ever.
- `zarch` counts positions in **PUSHes rather than pixels** (8.8), so the
  high byte of a position *is* the span boundary. `LD E,A` and the merge has
  its answer. Counting in pixels would have cost a shift per boundary and
  overflowed sixteen bits when a family of grid lines went nearly edge-on.
- `chequer`'s phase is the high byte of `i * camx`, accumulated with one add
  a period.

**What wraps for free, and what must not be masked back.** `roto`'s `u` is
masked to four bits of high byte every step, which is harmless because it
keeps `u` modulo 4096 and leaves the fraction alone. Doing the same to `v`
eats four bits of *its* fraction and the texture drifts — slowly enough to
look plausible, which is how the bug survived. Extract, do not write back.

**Signed comparison needs the overflow flag.** After `SBC HL,DE`, "less
than" is the sign flag *only* while the operands cannot differ by 32,768.
`cubes` hits exactly that: a cube at one wall is `2*XLIM` from the other,
the subtraction overflows, the sign says the opposite of the truth, and the
cube shoots across the room. `cb_cmp` reads overflow as well.

**And a 16-bit signed test on a byte is two compares.** `zarch`'s "is this
position at or past the right-hand edge, and not negative" is
`SUB 0x40 / CP 0x40`, true only for a high byte in 0x40..0x7F.

---

## 8. Do the arithmetic once and step it

**Bresenham, and what it really costs.** An edge is 39 T-states a scanline
*plus* 27 for every pixel it moves sideways (`render`; `renderlit` got the
travel down to 24 by inverting the branch so "x stays put" falls through).
On the logo that travel term averages 55 T-states a scanline and 46% of
edges are shallower than 45°, which is why a DDA rasteriser looked
attractive and why it still lost (§12).

**Affine in the right space.** `room3d`'s wall half-height is affine in
screen x, because 1/z is affine across a plane — so a wall's silhouette is a
straight line, the trapezoid raster is legal, and a wall running off the
screen is clamped by *interpolating h* rather than re-projecting.

**A screen row is one depth.** `zarch`'s whole renderer is this one
observation: with no camera roll, the ground line a row looks along is level,
so a family of parallel grid lines crosses it at even intervals, which
project to even intervals *on the row*. Each family is therefore an
arithmetic progression per row — a position and a step, both walked down the
screen by adding a constant. **No vertex is projected and no edge is
walked at all.**

**Count the steps and multiply once.** `zarch`'s setup walks out to the edge
of the screen a line at a time. Updating the rightmost line's slope and the
colour beyond it inside that loop cost 300 T-states an iteration; counting
the lines walked over and computing `d0 + k alphas` once at the end costs 40.

**Accumulate, do not recompute.** `chequer`'s per-band phase is one
subtraction of `camx`; `zarch`'s two steps and two positions are four adds a
row; `vox`'s ray is two 16-bit adds a sample. Anything that is linear down
the screen should be an add.

---

## 9. The cheapest pixel is the one you do not draw

**Dirty rectangles, erased through the stack.** `render` remembers the
bounding box of what each buffer holds and clears only that, at 5.5
T-states a byte instead of ~30: a mean erase of 12,642 T-states against
135,000 for the screen.

**Erase records per object, not per screen.** `stars` and `balls` each
remember, per object *per buffer*, the byte they last touched, and blank
that. Two buffers is why there are two sets of records: the byte to put back
is the one from two frames ago.

**Boxes, not their union.** `cubes` erases four separate boxes: the union of
four spread-out cubes is nearly the whole screen (135,000) and the four
boxes are 31,464.

**Draw the parts that never change once.** `chequer6`'s pilot stands on rows
48..143 and the board only draws from 97 down, so his top half goes into
both buffers at init and is never touched again — 183 bytes of stream a
frame rather than 565. `cubes`' viewport frame is painted once because the
room's own walls keep the cubes off it.

**Convexity means no overdraw and no sorting.** In a convex room the walls
tile the view exactly (`room3d`); cut a maze into convex sectors and the
doors partition the view, so `portal` recurses through them and still writes
every pixel exactly once.

**A horizon, not a z-buffer.** `vox` keeps the highest row drawn so far in
each column and only draws above it: **every screen byte is written exactly
once**, which no other renderer here can say. `wolf3d` prefills its viewport
and paints over 78% of what it wrote.

**Cull before you project.** `room3d` throws out walls off the side of the
screen on the signs of `vx−vz` and `vx+vz` at both ends — a tenth of the
cost of finding the same thing out afterwards.

**Cull in the space you are about to draw in.** `render`'s back-face test is
the sign of the cross product of two *projected* edges — two signed byte
multiplies, no normals, no 24-bit arithmetic — and it is exact with respect
to what is being drawn, so rounding can never let a back face paint over a
front one.

**Or cull with the normals you already have.** `renderlit` needs the real
normals for lighting, so its visibility test is `N·T + S·N·N < 0`, which for
unit normals is `N·T + S < 0` — the exact perspective test, almost free. And
a cube's face normals are the columns of its rotation matrix, so **one
matrix-transpose-times-vector gives all six faces at once** (3,050
T-states), twice a frame: once with the translation for visibility, once
with the light for shade.

**Order by separating planes, not by depth.** Sorting `prism`'s pieces on
centroid depth drew 344 pairs wrong in 178 frames of 256. For disjoint
convex prisms the separating axis theorem guarantees a separating *side
face* for every pair, and "is the eye outside this plane" is the same
`N·T + off < 0` test already being computed — so the ordering is a
topological sort over the pairs, and it is exact. Restrict the pairs to
those whose **screen boxes overlap**, or unrelated pieces invent cycles.

**Do not draw the faces nothing can see.** `prism`'s logo is a cut-up of
one plate, so ten of its 42 faces are joins buried inside the solid — and
because each pair has opposite normals, exactly one of every pair passes the
back-face cull every frame. Bit 7 of the face's normal byte says so (there
are 18 normals, so the bit was free): **4.6 faces and 429 pixels a frame,
12% of all the filling, and 42,914 T-states.** They are also what a wrong
painter order shows, so culling them makes most ordering mistakes invisible
as well as cheaper.

**Stop where the detail stops being worth it.** `harrier` gives the board up
to a haze below eight-pixel squares; `zarch` stops at 56 rows because the
rows near the horizon are where the span count runs away — 21 spans a row up
there against 5 at the bottom. `chequer5` measures what going all the way
costs: 14,527 T-states, which is exactly the wrong side of a 50 Hz frame.

---

## 10. Loops: the shapes that are cheaper than a loop

**No test at all.** `zarch`'s span player never tests for the end of a row:
the list's last entry points at a `JP` out of it. The loop is

    LD L,A / DEC A / DEC A / LD L,(HL) / JP (HL)

**33 T-states a span**, exit included, against the 63 `spanfill` measured
before the runs and the list were put in the same page. `LD L,(HL)` is what
does it: `H` never changes, so an entry byte goes straight into the low half
of the jump. A span of none lands on a `JP` at 64 and costs nothing extra,
and the second colour is the same entry with bit 7 set, so the entry byte
does not carry a colour at all.

**Count down so the flag is free.** `vox`'s ray step counts down and the
loop test is `DEC C` / `JP P` and nothing else; the tables are generated
with the step reversed to suit.

**Fall through the common case.** `renderlit`'s edge walk inverts its branch
so "x stays put" is the fall-through, which is most scanlines.

**Unroll to amortise the counter, not the work.** `balls`' blit wrote a byte
a pass — a store, an increment, a decrement and a branch, 27 T-states for
seven of work. Every row of a ball is an even number of bytes, so two a pass
halved the counter's share.

**`DJNZ` is 13/8 and `B` is precious.** Where `B` is wanted for something
else, a two-instruction chain entered n from the end beats reserving it.

**One `PUSH` writes two list entries.** `zarch`'s span list is built with
`PUSH AF` — the flags byte is junk and ignored — because 11 T-states for two
bytes beats 13 for one, and the list is read back in the same order it was
built by walking *downwards*.

---

## 11. Precompute the frame, if the frame fits

`prism` works its logo out live at 461,171 T-states — 13 Hz. `prismpre`
plays the same 256 frames back from 144 bytes a frame — 112 of projected
point, 21 of face shade, 7 of order and 4 of erase box — at 205,008
T-states, **29.3 Hz**, with the whole difference being that rotation,
lighting, projection and ordering happen in Python.

What it costs is memory and freedom: 11,776 bytes of points for the entropy
logo did not fit the 7,680 bytes above the screen buffers, so the points
went to a per-frame pointer table and `qsmul8` was stubbed out of that
harness to make room. A precomputed demo cannot be interacted with. The rule
of thumb the repo settled on: precompute the *pose*, keep the rasteriser
live.

The same idea in the small: `chequer6`'s sprite is a run-length stream where
**two thirds of the rows repeat the one above**, so 96 scanlines are 43 rows
of data; `twist`'s 64 silhouettes cover 256 angles because a square looks
the same every quarter turn — 2,240 bytes of run against 8,960.

---

## 12. Things that did not pay, with numbers

The negative results are the useful part of a repo like this.

**A DDA rasteriser instead of scanline arrays** (`polyfast`). Trades a
per-scanline win for a per-edge multiply: 6,204 T-states a face and 760.5 a
scanline against `renderlit`'s 3,040 and 798.5 at the time — break-even at
95 scanlines a face, and the logo's faces are 23. Then `renderlit` was gone
over again (2,274 and 713.5) and the two stopped crossing at all. Kept in
the repo, with its test printing both curves live so the comparison cannot
go stale.

**Removing the lighting to reach 25 Hz** (`prism`). Measured: it cannot,
because prism's non-drawing work alone is 213,320 T-states.

**Bit-sets in a byte** (`prism`). Eight pieces fit; the entropy logo has
nine, and the ninth silently mis-ordered. Widening the sets to words cost
the seven-piece shape 14,569 T-states — the price of a feature it does not
use.

**The palette as a free dimension** (`chequer` → `chequer4`). Flipping two
palette entries a scanline gives the board's depth stripes for nothing in
pixels, and the distance fade with them. But the flip moves with the camera,
so it is a table rebuilt every frame; it belongs to the buffer being
*displayed*, not the one being drawn; and the fill runs with `DI` and `SP`
walking the screen, so a line interrupt cannot be taken while it draws.
Moving the stripes into the pixels costs 80 T-states a scanline —
110,806 to 114,656 — and `demo/chequer4.gif` comes out byte for byte
identical to `demo/chequer3.gif`. **The palette is not free; it is borrowed
from the raster interrupt.**

**Estimates, generally.** `stars` was estimated at 300 T-states a star and
measured 1,030 — the estimate counted the plot and the erase and forgot the
reciprocal, the two signed multiplies, the byte address, the shade and the
two erase records. `vox` was estimated at 17 Hz and measured 19.2.
`zarch` was estimated at 200,000 and measured 208,206. The rule that came
out of it: **estimate the inner loop by counting instructions, and expect
the bookkeeping around it to be the larger half.**

---

## 13. How any of this is known

Every routine in this repo is verified **byte for byte against a Python
model** on an emulated Z80, over a sweep of inputs, and timed in T-states on
the same run. That is not ceremony — it is what makes the numbers above
worth writing down, and it caught, among others:

- `prism`'s side-face normals pointing *inward*, so three sides in four were
  culled that should have been drawn — and a face kept wrongly is wound
  backwards, fills nothing and simply vanishes — correctness, at +64,000
  T-states a frame;
- `chequer`'s whole board jumping a square sideways every 256 world units,
  found only when the tests were widened to camera positions outside one
  cell;
- `chequer`'s row step, where inverting one test put alternate rows 128
  bytes high — which, in the 0x2000 buffer, writes into the 0x8000 one;
- `roto`'s texture drift, which looks plausible;
- `twist`'s row pointer loaded before `EXX` instead of after, which set `SP`
  from garbage and pushed the runs over the low 8K;
- `zarch`'s row loop `CALL`ing while `SP` walked the screen, writing return
  addresses into the last two bytes of the row above.

The models are the specification, not a preview: `tests/zarch.py` does the
same 8.8 arithmetic in the same order as the assembly, so "the Z80 matches
the model" means something.

Two habits worth keeping:

**Measure the floor before building on it.** `spanfill.z80s` exists only to
answer "what does a flat-shaded span cost" (63.0 T-states, and 5.51 a byte)
because the answer decided whether a Zarch-style landscape was a 25 Hz
routine or a 12 Hz one. It turned out the dispatch could be halved again
once the runs and the list shared a page.

**Write the number down even when it says no.** `costs.md` has the table;
`demo-ideas.md` has the estimates, marked as estimates, and what they
measured when they were built.
