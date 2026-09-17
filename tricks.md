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
| a clear, `PUSH`, interrupt let in every 232 T | 7.33 | `scroll8` |
| a clear, `LD (HL),A` / `INC HL` | 13.25 | `scroll8` |
| a copy, `LDI` unrolled 64 | **16.16** | `scroll8`, `chequer6` |
| a span, `LD (HL),C` / `INC L` in pairs | 17.5 | `renderlit` |
| a flat column, no texture | 18.4 | `wolf3d` |
| a copy through the stack, eight bytes a block | 20.24 | `scroll8` |
| a copy, `LDIR` | 21 † | — |
| a textured column, two pixels wide | 22.8 | `wolf3d` |
| an `LD (HL),0` erase loop | ~30 | what `render` replaced |
| a textured column, stepping by a fraction | 72.6 | what `wolf3d`'s scalers replaced |
| **an arbitrary computed byte** | **109.7** | `roto` |

† an instruction timing, not a measured loop; everything else was timed.

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

**A fill is not a copy.** `PUSH` is unbeatable when the source is a
register and merely good when the source is memory, because a copy has to
move `SP` from the source to the destination and back, and there are only
twelve bytes of register to amortise that over. `scroll8` measures both
ends of it on the same 24K screen: clearing 1,024 bytes through the stack
is 7.33 T-states a byte against 13.25 for `LD (HL),A` / `INC HL`, and
moving 23,552 bytes through the stack is 20.24 against **16.16 for
unrolled `LDI`** — 18.86 of that even with the interrupt left alone.
Eight bytes of block cost 92 T-states of `POP` and `PUSH` — 11.5 a byte,
better than `LDI` — and then 58 more of stack pointer.

**One of the two pointers is always free, and never the one you want.**
`POP` walks up and `PUSH` walks down, so in a block copy either the source
or the destination ends up exactly where the next block needs it,
depending which way the blocks go — and which way they go is fixed by the
overlap, not by preference. `scroll8` moves the picture *down* memory, so
the blocks must run *up* it, so it is the source that lands right. It
cannot be spent either way: pointing `SP` at the other region is what
destroys it, and saving it across the block is `LD (nn),SP` and
`LD SP,(nn)`, 40 T-states against the 29 that keeping a pointer in the
alternate set costs.

**Letting the interrupt in.** A `PUSH` fill runs with `SP` inside the
screen, so an interrupt would push a return address into the picture:
`DI`. Anything longer than a frame therefore has to be cut into windows —

    DI / <work> / LD SP,IY / EI / NOP / DI ...

— and **the `NOP` is not padding**: `EI` does not take effect until after
the instruction that follows it, so `EI / DI` lets nothing in at all. The
caller's stack goes in `IY` because `LD SP,IY` is 10 T-states where
`LD SP,(nn)` is 20. Measured on `scroll8`, a window costs **22 T-states**,
and holding the interrupt off for no more than 322 T-states — 53.7 µs —
costs the routine **7.3%**.

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

**A whole-screen copy through the stack** (`scroll8`). `POP` and `PUSH`
move a byte in 11.5 T-states where `LDI` needs 16, and it still loses:
eight bytes is all the register there is, and the two `LD SP`s that
bracket them cost 58 T-states more. Measured over the 23,552 bytes an
eight-line scroll moves: 476,645 T-states through the stack against
380,552 by unrolled `LDI` — **25% slower, and the only one of the two
that has to turn the interrupt off.** The clear underneath it goes the
other way, 7,510 against 13,567, and that is the same fact from the other
side: the stack wins where the source is a register.

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
- `scroll8`'s blocks running down the screen instead of up, so each one
  carried off the source of a block 1,024 bytes further on — 22,440 of
  24,576 bytes wrong, in a picture that still looked like a picture.

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

---

## Paging is nearly free, and the address space is not the budget

`road2` compiles a run per road width and wanted 41,297 bytes of them.
Either side of two MODE 4 screens there are 15,800, so the first version
shared 38 quantised widths between 80 rows — and a shared width is a
staircase: the road's edge held its place for two rows in the middle
distance and four or five at the bottom.

A SAM has **256K in 16K pages**, and three facts make a bank of any size
cost almost nothing:

- **`VMPR` displays a page the CPU need not map.** Double buffering costs
  24K of address space, not 48K, which frees the whole low 32K.
- **A block's second section is always the page above the first** (`LMPR`
  gives page *n* at `0000` and *n+1* at `4000`), so you cannot hold half a
  block still. Page the bank with one register and the screens with the
  other, and duplicate the small resident part behind each screen — in the
  8K a 24K screen leaves at the end of its odd page.
- **`OUT (250),A` is 11 T-states.** If the drawing order walks the bank
  monotonically — `road2` draws rows widest first and cuts the bank in the
  same order — a bank of any size is two `OUT`s a frame.

What was surprising is that it *simplified* the routine. Per-buffer state —
which band each buffer last painted into each row — is duplicated correctly
by construction when the records sit behind the buffer they describe, so a
two-byte mark became one byte and the code that patched the row loop to
choose between them went. `rd2_back`/`rd2_front` went too: `HMPR` and
`VMPR` already know which buffer is which.

The rule that comes with it: **nothing in the duplicated block may carry
state from one frame to the next**, and the caller's stack must be in the
block that does not move.

---

## Stop patching: compile the loop instead

`chequer4`'s band loop sets a band up by patching six bytes into the row
loop — the row's last byte, the value set's address, whether the stack
pointer shifts, and the run to jump to. At 454 T-states a band that was a
quarter of `chequer5`'s frame, and the obvious answer, a precomputed table
of those six bytes, is worth much less than it looks: **six `LD (nn),A`
are 78 T-states of the 357 a table would replace**, and the table still
has to do them *and* read six bytes. ~284 against ~357.

The stores are the floor. So the thing to remove is the patching, not the
arithmetic: **compile the row loop itself, once per (band, phase), with
all six baked in**. The band loop then patches one address — the jump the
row loop turns round on — and a row costs what it always did.

    a band, patching six bytes        ~454 T-states
    a band, patching a table's six    ~284
    a band, patching one address      ~168      9,359 a frame, measured

It costs 2,080 copies of a 30-byte loop, which is 62K, which is why this
is a paging trick and not a 1990 one. Two things make it cheap to page:
the bodies are walked in draw order, and **a band uses exactly one run**,
so the runs can be cut by band alongside them — a chunk holds the bodies,
the runs, the values and the band table for a stretch of bands and needs
nothing from any other chunk. `chequer5` pages five times a frame.

The trap is worth knowing if you ever walk a table across chunks: the
terminator that says "switch" goes round the loop to be found, so anything
the top of that loop does — here, stepping the phase — happens one extra
time. Give it back at the switch.

## A sprite over a background that does not move is a run, not a stream

A masked sprite player costs what it costs because every byte is a
decision: an op to dispatch, and for the edge bytes a read, a mask and a
write. But a sprite drawn where **the background is one constant** needs
none of it. Bake the background into the sprite:

    transparent byte      the background's byte
    one pixel covered     the sprite's pixel, the background's other nibble
    fully covered         the sprite's byte

and what is left is a rectangle of constants, which is `LD SP` and a run
of `PUSH`es at 5.5 T-states a byte. It also **removes the clear**: the run
covers the whole box, so whatever was there before goes under it.

chequer6's pilot is 32x96 and half of him stands against a sky that has
one colour all the way across. That half was a run-length stream, masked,
with a `PUSH` clear before it: about 41,000 T-states between them. As a
compiled run it is **7,880**, and a frame that changes pose went from
200,875 to 159,388. The price is data — 1,486 bytes a pose against 400 —
so it wants the memory to have been found first.

The condition is exact and worth checking before you rely on it: *nothing
else paints those rows*. Put a scrolling city under the sprite and the
background stops being constant, the run has to go back to being a masked
stream, and the division between his halves moves (`chequer7`).

## Write the general case, then take the common one out of it

A routine that handles every case handles the usual one at the price of the
worst one, and the usual one is usually most of the frame.

chequer7 draws a band of city as rectangles: for each building, work out
where it lands, whether the screen's edge cuts it in two, how wide each
part is, whether a part's width is odd — `PUSH` writes two bytes — which
colours its leftmost pair takes, and where in a 64-`PUSH` fill block to
enter. That is about **800 T-states a building against 250 of pixels**.

But only a building the edge cuts can be in two parts, or have an odd
width, or want two colours. So: give the table four more bytes a building
— the fill block's entry for that width, and the address its top row ends
at when the offset is zero — and let the usual case read what it needs and
go. The general routine stays, for the one building a layer that is
actually cut.

    the band, one routine for every case      46,212 T-states
    the band, with the usual case lifted out  38,136      (-7,454)

The same shape appears in road2 (a row whose road is on screen needs no
stub and no spill repair; both exist for the rows that run off the edge)
and in chequer4's band loop. If a routine's setup is the same size as its
work, the question to ask is what fraction of calls needs all of it.

## A sprite that does not change is a routine, not data

A masked sprite player spends most of its time on decisions that were the
same last frame and will be the same next frame: which op this is, how many
bytes it covers, whether this one needs a mask. Only the *background* under
the sprite changes. So compile the sprite:

    a run of solid bytes   LD SP,end and a PUSH a pair - 5.5 T-states a
                           byte, with DE reloaded only where the pair
                           changes and SP only where a run does not carry
                           on from the one before
    an odd byte            LD A,n / LD (nn),A, because PUSH writes two
    one pixel of sprite    LD A,(nn) / AND / OR / LD (nn),A, which is the
                           only read-modify-write left

chequer6's pilot is 32x96 with 110 single-pixel bytes. Played from a
run-length stream he costs **63 T-states a byte on the screen**; compiled he
costs about **15**, and all 96 rows go down in 14,479 T-states where 63 rows
of stream cost 46,793.

Two things make it possible and one makes it worth it. Every address in the
compiled form is absolute, which needs **the back buffer at a fixed
address** - the paged map gives that for free, because `HMPR` maps whichever
buffer is being drawn to the same place. It is about four bytes of code a
pixel byte, so three poses came to 8,688 and needed **a page of their own**.
And what it buys is not just the T-states: with the whole sprite cheap
enough to redraw every frame, "drawn once per buffer" goes away, and with it
the clearing, the per-buffer bookkeeping and the rule that nothing may move
underneath it.

## Scrolling a picture by pixels: compile it per phase, spill the rest

A background that scrolls by whole bytes moves two pixels at a time. On a
slow layer that reads as scenery being dragged past; it is the single
biggest difference between chequer7's city and chequer8's desert, which are
otherwise the same idea.

Sub-byte scrolling of a whole row means the byte at every colour boundary
changes, so nothing can be worked out at run time - but everything can be
worked out in advance:

- **Compile the row, once per pixel phase.** Four phases means the run is
  entered at a pair (four pixels), the phase supplies the rest, and `SP`
  never has to take up an odd byte. Two phases is half the memory and wants
  an odd byte put back at the end of every row.
- **Hold two whole periods in the run**, so that entering it at the right
  pair gives any rotation of the pattern.
- **Stop the run where it should stop.** A run entered at *s* has `P - s`
  pushes left in it and a row wants 64, so the rest spill into the row
  above - draw the band bottom upwards and the next row covers them, at
  352 T-states a row on average and 704 in the worst frame. Better: carry
  the address of the 64th push in the entry, write a `JP` over the three
  bytes there and put them back afterwards. 144 T-states a row, no spill to
  repair, and - the part that matters - **the picture's cost stops
  depending on where it is scrolled to**.
- **Carry the entry points with the run**: a run reloads `DE` only where the
  colour changes, so an entry is (the `DE` it needs, where to go). Four
  bytes each, 64 of them, a quarter of a K a run.

The bill for chequer8's rear layer: 32 rows at four phases, 79K of bank,
45,938 T-states a frame, and a spread of 6,000 between its cheapest frame
and its dearest. In exchange, **detail is free**: a pyramid with two faces
and a course of stone in the light, palms, three ridges of dune, a scatter
of rocks. Drawn as rectangles at run time, in the city, every one of those
would have been another rectangle a row.

**Drive the offsets from the camera, not from a counter.** A layer at depth
Z moves `FOCAL * camx / Z` pixels when the camera slides, so a layer's
offset is a shift of the camera's own `camx` - and if two layers differ by
one shift, the near one is *exactly* twice the far one however the camera
moves, which a pair of divisions would not be. chequer8 triples `camx` and
shifts it five places and six: about 130 T-states, and the difference
between scenery that belongs to the ground and scenery that drifts past on
a clock of its own. The fudge to know you are making: anything drawn above
the horizon is strictly at infinity and has no parallax at all.

A second layer over the top cannot share any of it, because the two layers
move at different rates: it goes on as spans, with a read-modify-write at
either end where the edge lands inside a byte. **That read-modify-write is
what lets the near pyramids pass in front of the far one** - 45 T-states an
edge, twice a span, and the reason the front layer costs 590 T-states a span
where the rear layer draws a whole scanline for 1,200.

## A table indexed by distance from the horizon serves every horizon

Moving the horizon looks like it multiplies every table by the number of
positions it can take, and on a machine with 32 pages that ends the idea
before it starts. It does not, and the reason is worth keeping:

    a square's width at row y      round(S * (y - horizon) / CAMH)
    a scanline's depth             CAMH * FOCAL / (y - horizon)

**Both are functions of the row's distance from the horizon and of nothing
else.** A row 40 scanlines below the horizon is the same row wherever that
is on the screen. So:

- **the band table is one table**, and a taller board starts further down
  it, at the band holding the bottom row of the screen. The bands before
  that one are the ones that would be off the bottom.
- **the depth-indexed tables are the same tables**, only generated as deep
  as the deepest board and copied as far as the horizon says. chequer9's
  swap masks are 512 of them and the copy is 128 `LDI`s entered at
  `2 * (128 - rows)`: 1,450 T-states at 77 rows of board and 2,042 at 114,
  against the 6,200 to 9,300 that computing the mask a scanline again would
  have cost. This was expected to be the bill for a moving horizon and it is
  the cheapest thing in it.
- **what does change is the widest square**, because pitching the horizon up
  brings coarser ground into view. chequer9 compiles up to 96 pixel squares
  rather than 64: 4,656 bodies against 2,080, which is the whole price and
  it is paid in pages rather than T-states.

**A horizon is allowed when the screen's bottom row is the last row of its
band**, because a band is drawn whole - 32 of the 39 rows in chequer9's
range are, a horizon every scanline or two. Five bytes a horizon say which
chunk the bottom band is in, where in its table, how many scanlines, and
the widest square, which is what the phase accumulator is seeded with; that
last one is a different square at every horizon, so six shifts become a
shift-and-add multiply.

**And what shrinks has to be put back.** When the horizon rises, the rows
the board and the band give up are sky, and nothing else paints them. With a
copy of the resident block behind each buffer, each buffer's record of what
it was last drawn with is free and needs no keeping in step - and a buffer
that skipped a step puts back both at once.

## A compiled sprite that can move: walk SP down the whole thing

A compiled sprite with absolute addresses cannot move. The way to make one
relative on a Z80 is `SP`, because it is the only pointer with an add, and
the way to keep that cheap is to arrange the whole sprite as **one
descending walk**: rows bottom upwards, bytes right to left, so every step
is a subtraction and the caller's only job is to put `SP` at the byte after
the bottom right corner.

| | |
|---|---|
| a run of solid bytes | `PUSH DE` a pair - 5.5 T-states a byte |
| a single byte | `POP BC / LD C,n / PUSH BC`, which reads its neighbour and writes it back unchanged |
| one masked byte | `POP BC / LD A,C / AND m / OR v / LD C,A / PUSH BC` |
| a step | `LD HL,-d / ADD HL,SP / LD SP,HL`, or `DEC SP` where the step is small enough |

chequer9's pilot is 96 rows in **16,116 T-states against the absolute
version's 14,401** - 12% for being able to put him anywhere on the screen,
and no `DI` window longer than the sprite itself. He still moves in whole
bytes sideways: a pixel of horizontal travel would want him compiled at both
phases and a mask on *every* byte rather than the 110 his outline needs.

## Every CALL is a bet that the page underneath it has not moved

A `CALL` writes the return address to the stack in whatever page is mapped
now, and the `RET` reads it from whatever page is mapped then. Page memory
in between and it reads someone else's bytes - silently, and a long way from
where the mistake is.

This bit twice in one afternoon. `c9_band` pages the desert's chunks in over
the board's bank, and the caller's stack is in chunk 0: a `CALL c9_chunk`
that ended with the new chunk mapped returned into the middle of a compiled
run. Inlining the switch fixed it. Then the same routine returned to *its*
caller with the last desert chunk still mapped, and the frame ended in the
weeds.

The rules that came out of it, for any routine that pages:

- put the caller's page back before returning;
- never `CALL` across a switch - inline it, or jump;
- and if the routine also puts `SP` on the screen, put *that* back before
  anything calls anything.
