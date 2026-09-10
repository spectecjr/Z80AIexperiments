# costs.md — what everything measured, and what was tried and dropped

Every number here was measured on the emulated Z80 by `tests/`, not estimated.
T-states are raw: real SAM screen contention is on top. A 6 MHz SAM has
**120,000 T-states between 50 Hz interrupts** and **240,000 at 25 Hz**.

Where a routine was changed, the before and after are both kept, because the
useful part is usually the size of the step rather than the final figure.

---

## 1. The demos

| | T-states a frame (min / mean / max) | Hz | |
|---|---|---|---|
| `chequer4` | 110,835 / **114,656** / 118,586 | **50** | the floor with its depth stripes in the pixels |
| `chequer5` | 125,343 / **129,183** / 133,151 | 25 | the same routine, board all the way to the horizon |
| `chequer6` | 150,767 / **154,607** / 158,575 | 25 | and a pilot in a jetpack over the top of it |
| `chequer3` | 106,970 / **110,806** / 114,736 | **50** | the same picture, stripes in the palette |
| `prismpre` | 121,498 / **205,008** / 255,774 | **29.3** | the provisional logo, frame precomputed |
| `entropypre` | 118,994 / **220,823** / 292,156 | **27.2** | the traced artwork, nine pieces |
| `democube` + `renderlit` | 102,854 mean | 50 (86% of the budget) | one lit cube |
| `cubes` | 371,142 / **419,478** / 472,588 | 14.3 | four lit cubes, gravity, wire room |
| `prism` | 366,000 / **461,171** / 519,000 | 13.0 | the provisional logo, worked out live |
| `prism`, entropy | 434,299 / **550,669** / 631,969 | 10.9 | the traced artwork, live |
| `portal` | 400,481 mean | 15 | sector walk, screen-x windows |

## 1a. The floors, measured

| | T-states | |
|---|---|---|
| a flat-shaded span (`spanfill`) | **63.0** | plus 5.51 a byte, which is `PUSH`'s floor |
| a scanline of it | 92 | 128 rows of full-width floor is 101,888 |
| an edge stepped a scanline (`renderlit`) | 39 | what produces a span |

Which is what `demo-ideas.md` §15 costs a Zarch-style polygon landscape
against: about eight cells across a 128-scanline floor at 25 Hz.

## 2. The rasteriser (`renderlit`), before and after

Measured by timing `rndl_six` on one quad of a known size.

| | a face | a scanline | filling |
|---|---|---|---|
| before | 3,040 | 798.5 | 17.5 T-states a byte |
| **after** | **2,274** | **713.5** | unchanged |

A 40×32 quad went 28,592 → 25,106 upright, and 32,560 → 28,178 with its
edges leaning 64 pixels over. Nothing changed a pixel: all ten tests still
match their models byte for byte.

**The shape of the workload is why.** Over prism's 256 frames:

| | |
|---|---|
| spans a frame | 298 |
| mean span | **5.9 bytes** |
| one byte | 10% of spans |
| four bytes or fewer | 47% |
| eight or fewer | 80% |
| scanlines a frame | 301 |
| faces drawn a frame | 13.3 |
| **filling, a frame** | **36,000 T-states** |
| **overhead, a frame** | **128,000** |

So the fill is not the cost; the per-span fixed cost is. Where 431 T-states
of per-scanline overhead used to go:

| | T-states |
|---|---|
| two edge walks | 78, plus 27 a pixel of sideways travel (55 a scanline on the logo; 46% of edges are shallower than 45°) |
| reading `xl`/`xr` back across the register sets | 55 |
| span setup — byte addresses, two end masks | ~120 |
| loop — empty test, line step, call, DJNZ | ~90 |

### What took it to 713.5

| | saved |
|---|---|
| end masks as immediates, branching on the parity of x | ~26 a span, 68 on one-byte spans |
| screen pointer into the other register set, arrays read in the main one | 29 a scanline, plus the `PUSH BC`/`POP BC` around the span |
| the span written out rather than called | 17 a span |
| the edge walk's branch inverted so "x stays put" falls through | 5 a scanline; travel 27 → 24 a pixel |
| the gather written out — 91 T-states a point against 149 | ~240 a face |
| the six-face dispatch walking pointers instead of a memory index | ~340 a call |

Then both prisms stopped using `rndl_setface` and `rndl_six` altogether and
call `rndl_quad` for the faces they actually draw: 42 faces of bookkeeping a
frame for the 13 that get drawn. A frame of prismpre that draws *nothing*
cost 38,079 T-states, 18,700 of it above the erase.

    prism      457,869 -> 446,602
    prismpre   210,693 -> 204,625

## 3. Where a frame goes now

**prism** (446,602):

| | T-states | |
|---|---|---|
| `pr_draw` | 197,046 | 44% |
| `pr_proj` | 83,969 | 19% — 56 corners projected, seven screen boxes |
| `pr_light` | 73,704 | 17% — half of it is the visibility test |
| `pr_order` | 33,161 | 7% — 21 separating planes, topological sort |
| `pr_tables` | 27,649 | 6% |
| `rndl_erase` | 24,022 | 5% |
| `demo_spin` | 6,628 | 1% |

**prismpre** (204,625): the erase is 22,766 and the drawing 181,858. Nothing
else happens at all.

## 4. Things that were tried and kept

| | measured |
|---|---|
| **Cull the faces buried inside the solid.** Ten of 42 faces are joins between pieces; their normals are opposite so one of each pair passes the cull every frame — 4.6 faces and 429 pixels of fill a frame, 12% of all filling. | prism −42,914 a frame |
| **Order the pieces by separating planes** rather than centroid depth. A centroid drew 344 pairs the wrong way round in 178 of 256 frames; the planes leave 36 in 36. Costs 33,161 against the centroid sort's 18,835 — and it also needs the projection moved ahead of drawing. | correctness, +14,000 |
| **Precompute the whole frame** (`prismpre`): spin, multiply tables, 56 projected vertices, 18 normals' shade and eye test, and the sort. | −248,000 a frame |
| **Fix the side faces' normals.** They pointed inward, so three sides in four were culled when they should have been drawn — and a face kept wrongly is wound backwards, fills nothing, and vanishes. | correctness, +64,000 |

## 5. Things that were tried and dropped, with the numbers

| | measured | |
|---|---|---|
| **Merge the coplanar front faces** into one polygon a group | ceiling ~26,000 a frame: 3.7 fewer faces and 30 fewer spans of 120 | only 25% of spans merge, and the merged outline needs 1 to 4 spans a scanline, so it wants an active edge table whose crossing sort costs about what the merge saves |
| **`polyfast`** — chains walked as an 8.8 DDA in a register pair, no scanline arrays | 6,204 a face + 760.5 a scanline, against renderlit's 2,274 + 713.5 | the scanline did get cheaper and flat in the slope, but a DDA needs a step an edge where Bresenham needs none. It broke even at 95 scanlines a face when renderlit was at 3,040 + 798.5, and prism's faces average 23. Kept as `polyfast.z80s` and `polyfast.md` |
| **Split prismpre's erase box** — one for the sigma, one for the triangle | blanks 94% of the bytes one box does; a box a piece blanks 115% | the pieces' boxes overlap too much |
| **Drop the lighting from prism** (flat faces, visibility kept) | 446,602 → **410,789**, 14.6 Hz | `pr_light` 73,704 → 37,891; the other half *is* the visibility test. prism's non-drawing work is 213,320 even with no lighting at all — 89% of the whole 25 Hz budget — so no lighting setting reaches 25 Hz |
| **Divide to get a DDA step** rather than a reciprocal table | `pf_div` 850 T-states against 342 for two quarter-square multiplies | the table (384 bytes) won, but not by enough to save the design |

## 6. Sizes, and what the shape costs

| | |
|---|---|
| **half-size logo** (measured at the 518,273 baseline) | 377,195, 15.9 Hz — a quarter of the pixels buys 27%, not 75%, because 273,000 was a floor that no size touched |
| **prismpre's tables** | 144 bytes a frame — 112 of point, 21 of face nibble, 7 of order, 4 of erase box — and the free RAM holds **64 frames, not 68**, which is what fixes the loop length and the turn rates |
| **two cubes** | 245,765, 24.4 Hz |
| **three cubes** | 348,318, 17.2 Hz |
| **four cubes** | 449,675 → 419,478, 14.3 Hz |
| a cube | ~102,000, on ~42,000 of fixed cost |
| the wire room's eight edges alone | 56,000 |

## 7. The floors

| | T-states |
|---|---|
| a constant run pushed onto the screen | 5.5 a byte |
| a run stored `LD (HL),C` / `INC L`, unrolled in pairs | 17.5 a byte |
| an arbitrary computed byte | 109.7 |
| a whole screen of compiled runs | 135,000 |
| `qsmul8`, 8×8 → 16 | 131 |
| `pf_div`, 16÷8 | 850 |
| `rndl_erase`, prismpre's box | 22,766 |
| a scanline of renderlit, before it fills anything | ~373 |

## 8. The two logos

The provisional shape is seven convex pieces; the artwork traced from
`entropylogo.png` is nine, because the sigma's bar ends are cut back to
points and its left edge is notched. `PRISM_SHAPE=entropy` builds it.

| | provisional | entropy |
|---|---|---|
| pieces | 7 | 9 |
| faces | 42 | 54 |
| buried faces, never drawn | 10 | 14 |
| distinct normals | 18 | 21 |
| ordering pairs, which grow as n² | 21 | 36 |
| prismpre's table a frame | 144 bytes | 184 |
| **prism** | 461,171 | **550,669** (+19%) |
| **prismpre** | 205,008 | **220,823** (+8%) |

Nine pieces cost prismpre only 8% because most of its frame is the fill,
and the extra pieces are small. prism pays 19%, because `pr_proj` is per
piece and `pr_order` is per pair.

Two things had to change to carry nine pieces:

- **`pr_order`'s sets are words now, not bytes.** A bit a piece in a byte
  is eight pieces, and the ninth needs sixteen. That costs the seven-piece
  shape 14,569 T-states a frame - prism went 446,602 → 461,171 - and costs
  prismpre nothing, because its order is a table.
- **The points no longer fit in one place.** 184 bytes a frame over 64
  frames is 11,776, and above the screen buffers there are 7,680. So a
  frame's points are found through a table of pointers: 53 frames of them
  live high, eleven down in the low 8K beside the records. The
  quarter-square multiply goes too - prismpre never multiplies, and
  renderlit only names `qsmul8` from paths it never calls - which is 1,280
  bytes back.

## 9. What is left, in order

1. **The span setup**, ~160 T-states a scanline of byte addresses and end
   masks against 17.5 a byte of filling. 298 spans a frame.
2. **Draw the triangle once and leave it.** If only the sigma turns, the
   triangle comes out of the erase box as well as the draw: measured, it is
   **38% of the faces drawn and 41% of the scanlines**.
3. **Fewer, larger convex pieces.** Seven is what the shape needs, not the
   renderer.
