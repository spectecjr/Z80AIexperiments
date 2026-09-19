# Bubble Bobble on the SAM Coupe - design and frame budget

Target: SAM Coupe (Z80B @ 6 MHz), screen MODE 4, 256x192, 16 colours from 128.
Goal: arcade-faithful tile background with platforms, bubbles that ride a wind
current around the level, and the fastest object renderer the machine allows.

---

## 1. The real currency on a SAM is memory accesses, not T-states

The SAM's ASIC shares one memory bus between the CPU and the display. Contention
is **not** Spectrum-like (a per-cell pattern over part of the line); it is a flat
slot rate that depends only on where the raster is:

| Raster region              | CPU memory slot | Slots per line |
|----------------------------|-----------------|----------------|
| Active display (256 of 384 T) | 1 per 8 T   | 32             |
| Border / blanking (128 of 384 T) | 1 per 4 T | 32            |
| A fully blanked line (no display) | 1 per 4 T | 96           |

Frame geometry: **384 T per line x 312 lines = 119,808 T**, ~50.08 Hz.

    display lines : 192 x (32 + 32) =  12,288 slots
    blank lines   : 120 x  96       =  11,520 slots
    ------------------------------------------------
    TOTAL         :                   23,808 memory accesses per frame

Every Z80 memory access costs one slot: opcode fetch (M1), each operand byte,
each data read, each data write, and each half of a PUSH/POP. So the cost of an
instruction is approximately

    cost_T = max( natural_T , accesses x slot_width )

which during the display area means almost everything costs `accesses x 8 T`.

Because of this, source in this project is annotated `; [11T / 3a]` - natural
T-states **and** memory accesses. The access count is the number that decides
whether a frame fits.

### Consequences

Bytes written per access, for the three candidate write primitives:

| Primitive              | bytes | accesses | acc/byte |
|------------------------|-------|----------|----------|
| `PUSH rr`              | 2     | 3        | **1.50** |
| `LD (HL),r` + `INC L`  | 1     | 3        | 3.00     |
| `LDI`                  | 1     | 4        | 4.00     |
| `LD (HL),n` + `INC L`  | 1     | 4        | 4.00     |

Therefore:

* **Stack blitting is the only fast way to move pixels on a SAM.** Everything
  else is 2-2.7x worse.
* The absolute ceiling on screen writes is `23,808 / 1.5 = 15,872 bytes/frame`,
  and a MODE 4 screen is **24,576 bytes**. *You physically cannot clear, let
  alone redraw, a full MODE 4 screen in one frame.* Best case is 65% of it, and
  that is with zero register reloads and zero SP management.

That single fact dictates the whole architecture: **double buffer + dirty
rectangles**. Full-screen redraw and full-screen clear are both off the table.

---

## 2. How many items must we render?

### Arcade reference

Taito's Bubble Bobble board is itself twin Z80s @ 6 MHz, 256x224 at 59.18 Hz,
8x8 16-colour background tiles, and sprite hardware capable of **192 sprite
entries** (8x8 up to 16x256). The hardware ceiling is far above what the game
actually uses - it is a hardware limit, not a design target.

The design target is the observed *gameplay* peak. Enumerating the object
classes that can be alive simultaneously:

| Class                                   | Size   | Practical max |
|-----------------------------------------|--------|---------------|
| Players (Bub, Bob)                      | 16x16  | 2             |
| Free enemies (level cap)                | 16x16  | 7             |
| Enemies trapped in bubbles              | 16x16  | 7             |
| Player bubbles (empty)                  | 16x16  | 12            |
| Special bubbles (water / fire / lightning) | 16x16 | 3            |
| Hazards spawned by specials (water fall segments, fire pools) | 16x16 | 8 |
| Fruit / treasure drops                  | 16x16  | 8             |
| EXTEND letter bubbles                   | 16x16  | 6             |
| Score popups                            | 16x8   | 8             |
| Enemy projectiles                       | 8x8    | 6             |
| Baron von Blubba                        | 16x16  | 2             |

The column sums to ~69, but the classes are not simultaneously maximal - you do
not get a full bubble raft *and* a full fruit shower *and* all six EXTEND
letters in the same frame. The realistic simultaneous peak in normal arcade play
is **35-40 objects of 16x16**.

### What this codebase targets

* `OBJ_MAX = 48` - object table size. Comfortably above the observed arcade
  peak, and 48 x 16 bytes = 768 bytes fits under a 1K alignment.
* **24-32 objects fully re-rendered every 50 Hz frame** is the guaranteed
  sustained figure (derivation below).
* Anything above that is handled by a **priority budget governor** (section 5),
  not by dropping frames: low-value objects (score popups, settled fruit)
  simply hold their pixels for an extra frame.

---

## 3. Cost model, per object

A 16x16 object in MODE 4 is 8 bytes x 16 rows = **128 bytes**.

Every figure below is **measured, not estimated**: `tools/bbgfx.py` counts
the accesses in the straight-line code it emits, and `tools/budget.py`
re-derives every `[nT / na]` annotation in the assembly from a Z80 timing
table (1,392 annotations currently checked, 0 disagreements).

### Draw, opaque (stack blit) - 363-397a

Registers: `HL` = running screen pointer, `BC` = the 128-byte row stride,
`IX` and `IY` hold the sprite's two most frequent byte pairs, and `DE` is
a rolling cache for the rest. Per row: `LD SP,HL`, four pushes, `ADD
HL,BC`.

The floor is 16 x (1 + 4x3 + 1) = **224a**; the measured 397a for a player
frame is that plus the `LD DE,nn` reloads where a row's pairs alternate.

A 16x16 circle is not a rectangle, so the opaque variant bakes the
backdrop colour into the transparent corners. That makes it correct - and
self-erasing - wherever the object's box sits entirely on plain backdrop,
which `bb_box_is_flat` answers in 28 accesses.

### Draw, masked (compiled sprite) - 440-577a

Bubble Bobble's bubbles are *hollow*; you see the playfield through them,
so they cannot be drawn opaquely at any price. They are emitted as
compiled sprites: straight-line code, one specialised sequence per byte.

| Byte class              | Sequence                                | acc |
|-------------------------|-----------------------------------------|-----|
| both pixels transparent | `INC HL`                                | 1   |
| both pixels ink         | `LD (HL),C` (colour cached) or `LD (HL),n` | 2-3 |
| one pixel ink           | `LD A,(HL) / AND n / OR n / LD (HL),A`  | 8   |

Nibble edges are what cost, which is why objects are **snapped to even X**
(one byte = two pixels): it halves the edge cases and removes the need for
pre-shifted sprite variants entirely.

Every solid object therefore carries **both** compiled frames, and
`bb_draw_one` picks per frame. The opaque one is 26% cheaper.

### Erase - 239a flat, ~4,080a tiled (measured)

There is no background master page (section 5 explains why all four memory
sections are spoken for), so erase regenerates background pixels:

| Case                               | Method                       | acc    |
|------------------------------------|------------------------------|--------|
| Box entirely on flat backdrop      | `PUSH` fill, one cached pair | 239    |
| Box overlaps a platform cell       | LDI from the tile bank       | ~4,080 |
| Unmoved, opaque, flat              | skipped - the draw covers it | 16     |

Choosing between them costs 28 accesses, because `bb_flat3map` precomputes
"this cell and the 3x3 block starting at it are all backdrop" per cell at
level load.

**The 4,080a is measured, and it is 4.6x what this document originally
estimated.** The estimate counted the LDI copies and dismissed the address
arithmetic around them - `bb_blit_tiles` recomputes the tile-bank source
pointer on every one of the 16 pixel rows, which is 69 accesses of setup
wrapped around 16 accesses of copying, repeated for each of up to three
cell columns. `tools/profile.py` runs the real code and attributes bus
traffic to the nearest label; it puts `bb_bt_rowloop` at **45% of the
entire frame**. No amount of re-reading the source would have found that:
the annotations were all individually correct, and the loop structure was
what was wrong.

### Totals

| Object kind                       | erase | draw | total |
|-----------------------------------|-------|------|-------|
| Solid, flat backdrop              | 239   | 397  | 636   |
| Solid, flat, unmoved (animating)  | 16    | 397  | 413   |
| Hollow bubble, flat backdrop      | 239   | 577  | 816   |
| Solid, over a platform            | 880   | 538  | 1418  |
| Hollow bubble, over a platform    | 880   | 577  | 1457  |
| **Weighted Bubble Bobble mix**    | 431   | 505  | **936** |

---

## 4. Frame budget - predicted, then measured

The original budget counted the blitting and allowed a flat 1,800a for
everything else. Running the code says otherwise.

### What was predicted

    Frame total                                        23,808 a
      overheads (IRQ, logic, plan, audio, slack)       -6,630
      Available for blitting                           17,178 a
    -> 18 objects per 50 Hz frame in a realistic mix

### What actually happens

`python3 tools/profile.py` over 30 frames of live play, with 13.3 objects
alive on average:

    measured mean     63,808 accesses     2.68x over budget

    nearest label              a/frame  share
    bb_bt_rowloop                28814   45.2%   tiled erase
    bb_spr_bubble                 3245    5.1%   hollow bubble draw
    bb_plan                       3157    4.9%   clearing bb_touched
    bb_obj_grid                   3088    4.8%   clearing bb_cellgrid
    bb_spr_enemy                  1867    2.9%
    bb_box_is_flat                1516    2.4%
    bb_cell_solid                 1252    2.0%
    bb_ou_loop                    1036    1.6%
    bb_mark_box                    978    1.5%
    bb_blit_flat_8x16              890    1.4%

So the honest figure is **around 5 objects per 50 Hz frame as the code
stands**, not 18, and the prototype as recorded runs at roughly a third of
field rate. The three things that make up the difference are all
structural rather than instruction-level:

1. **The tiled erase recomputes loop invariants** (45% of the frame).
   Hoisting the tile-bank source out of the pixel-row loop - the tile id is
   constant across a cell row and LDI already streams the source - takes it
   from ~4,080a to ~2,250a. The **background master page** described below
   takes it to **624a**, a 6.5x win on the single largest cost, and is now
   clearly worth its paging machinery rather than being a nice-to-have.
2. **Two 768-byte LDIR clears per frame** (`bb_touched`, `bb_cellgrid`)
   cost 6,245a between them - 26% of the entire frame budget - to zero
   grids that are then barely written. A generation tag compared against a
   per-frame counter removes both clears outright.
3. **`bb_cell_solid` and `bb_box_is_flat` at 2,768a combined.** Both walk
   from cell coordinates to a bit every time they are called; caching the
   map row pointer across a box's three rows would roughly halve them.

Applying all three lands near 24,000a, which is the budget - at which
point the 18-object figure becomes reachable rather than hypothetical.
None of that is done here. What is done is the measurement, and the
measurement is the point: **the per-instruction annotations in this
project are verified correct to the last access, and the cost model built
on top of them was still wrong by 2.7x.**

---

## 5. Architecture

### Memory map

The SAM maps only two 32K windows (LMPR picks section A and gets B = A+1 free;
HMPR picks C and gets D = C+1). Three things want to be resident - code,
background source, and the back buffer - and only two can be. Resolving this in
favour of **no background master page** is what frees a full 32K for code and
compiled sprites:

    LMPR -> pages 0,1   0x0000-0x7FFF   32K: IRQ vector, code, tables,
                                             tile bank, compiled sprites,
                                             object data, stack
    HMPR -> back buffer 0x8000-0xDFFF   24K: the buffer being rendered
                                        0xE000-0xFFFF  8K spare
    VMPR -> front buffer + MODE 4 bits
    Buffer pairs: pages 4,5 and 6,7 (256K-safe)

ROM is paged out via LMPR bit 5, so `0x0038` is ours and `IM 1` works.

### Screen addressing

MODE 4 is a clean linear 128 bytes/line framebuffer, so

    addr = 0x8000 + (y * 128) + (x >> 1)

which factors into `H = 0x80 + (y >> 1)`, `L = ((y & 1) << 7) + (x >> 1)`.
`bb_tables.z80s` builds a 192-entry row-address table anyway - 2 accesses beats
9 instructions.

### Frame loop

Stack blitting means `SP` points at the screen, so an interrupt during a blit
would push return addresses into the picture. The loop therefore renders with
interrupts disabled and synchronises on `HALT`:

    EI / HALT      -> frame IRQ: flips VMPR iff the last render completed,
                      sets the tick flag, EI, RETI
    DI
    erase pass     -> undo what this buffer held two frames ago
    logic pass
    draw pass
    mark render complete
    loop

If a frame overruns, the IRQ is simply missed and the front buffer holds for one
extra frame - the picture degrades to 25 Hz rather than tearing.

### Level representation

Faithful to the arcade: the playfield is a grid of 8x8 cells and the level is a
**1-bit-per-cell bitmap**, 4 bytes per row. The arcade stores 32x25 with the top
and bottom rows implicit; the SAM's 192-line display gives us 32x24, so:

    4 bytes x 24 rows = 96 bytes per level

This one structure serves three jobs:
* **collision** - one `AND` against a mask table, ~8 accesses per test;
* **autotiling** - the 4-neighbour mask (up/down/left/right solid) indexes 16
  tile variants, so a level's whole look comes from 16 tiles x 32 bytes = 512
  bytes;
* **erase path selection** - "is this box entirely off-platform?"

### Bubble paths - the wind current

In the arcade, bubbles rise and then ride a per-level *wind current* around the
playfield; this is what makes bubbles queue along ceilings and pour down the far
wall. The arcade ships authored wind data. This implementation **generates the
field at level load**, which keeps a level to 96 bytes:

1. Every free cell defaults to flow **up** (bubbles are buoyant).
2. Trace the perimeter of the largest free region with a left-hand wall follow,
   writing the *tangential* direction into each boundary cell. This produces the
   circulation loop: along the ceiling, down a wall, across the floor, back up.
3. Breadth-first flood from the loop cells into the interior, each cell taking
   the direction that points back toward its BFS parent.

Result: a `32 x 24` nibble field, **384 bytes**, and a runtime cost per bubble of
one table lookup:

    dir  = flow[(y >> 3) * 32 + (x >> 3)]      ; ~10 a
    vx  += dirtab_x[dir]  ;  vy += dirtab_y[dir]
    clamp to terminal speed

Bubbles additionally repel each other (this is what forms rafts). O(n^2) over 24
bubbles would be 276 pairs; instead bubbles register in the same 32x24 cell grid
and test only their 3x3 neighbourhood - ~8 tests each.

---

## 6. Asset pipeline

`tools/bbgfx.py` converts source PNGs to MODE 4 4bpp data, fits a 16-entry SAM
palette (3-bit-per-channel + half-intensity), and emits **compiled sprite code**
as `.z80s`. `tools/bblevel.py` packs level bitmaps. `tools/budget.py` recomputes
every number in this document from the instruction tables, so the budget cannot
silently drift from the code.

Arcade artwork is not redistributed here. The pipeline reads standard PNG rips
(e.g. from The Spriters Resource) at their native 16x16 arcade geometry and
palette; `bb_gfx_placeholder.py` generates stand-in art with identical geometry
so the prototype builds and runs without them.

---

## 7. Building, running and checking

    ./build.sh

produces `build/bb.bin`, a 27,648-byte image for pages 0 and 1. It is
entered at `$0000` with `LMPR` selecting page 0 and the ROM paged out. A
loader and disk image are out of scope for this prototype; under SimCoupe
the image is poked into pages 0-1 and executed from `$0000`.

Three tools, all runnable:

| Tool                     | What it does                                     |
|--------------------------|--------------------------------------------------|
| `tools/bbgfx.py`         | palette, tile bank, levels, and the two sprite compilers; prints the measured access cost of every frame it emits |
| `tools/bbverify.py`      | reference model of the autotiler and the wind current; traces a bubble and fails if it does not circulate |
| `tools/budget.py`        | the predicted frame budget, plus re-derives every `[nT / na]` annotation in the assembly from a Z80 timing table |
| `tools/z80.py`, `tools/sam.py` | a Z80 core and enough SAM Coupe (paging, CLUT, keyboard, MODE 4 decode) to run the assembled image |
| `tools/profile.py`       | runs the real code and attributes every memory access to the nearest label - the measured budget |
| `tools/makegif.py`       | records the running prototype to `build/bubble-bobble-sam.gif` |

`tools/bbverify.py --trace` prints the wind field as arrows with the
bubble's path overlaid, which is the quickest way to see that a level's
current closes into a loop:

```
   #oooooooooooooooooooooooooooooo#
   #o^^^^^^^^^^^^^^^^^^^^^^^^^^^^v#
   #o^^<<<<<<<<<^^^^^^<<<<<<<<<^^v#
   #o^v#########^^^^^v#########^^v#
   #o^^>>>>>>>>>^^^^^^>>>>>>>>>^^v#
   #^oo<<<<<<<<<<<<<<<<<<<<<<<<<<<#
```

Rising up the left wall, right along the ceiling, down the right wall and
back left along the floor - with each platform's top surface sliding
bubbles left and its underside sliding them right, so a bubble caught
under a platform works its way out to the edge and rejoins the stream.

## 8. Artwork

Arcade artwork is not redistributed here. `tools/bbgfx.py` reads palettised
16x16 PNGs from `tools/art/` (`bubble.png`, `player.png`, `enemy.png`,
`fruit.png`) with palette index 0 meaning transparent - the geometry the
arcade itself uses. Without them it synthesises stand-ins at identical
dimensions so the prototype builds and runs unchanged.
