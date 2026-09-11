# costs.md — what everything measured, and what was tried and dropped

Every number here was measured on the emulated Z80 by `tests/`, not estimated.
T-states are raw: real SAM screen contention is on top. A 6 MHz SAM has
**120,000 T-states between 50 Hz interrupts** and **240,000 at 25 Hz**.

Where a routine was changed, the before and after are both kept, because the
useful part is usually the size of the step rather than the final figure.

`tricks.md` is the other half of this file: the techniques these numbers
came out of, what each one costs, and where it does not pay.

---

## 1. The demos

| | T-states a frame (min / mean / max) | Hz | |
|---|---|---|---|
| `chequer4` | 110,835 / **114,656** / 118,586 | **50** | the floor with its depth stripes in the pixels |
| `chequer5` | 125,343 / **129,183** / 133,151 | 25 | the same routine, board all the way to the horizon |
| `chequer6` | 150,767 / **154,607** / 158,575 | 25 | and a pilot in a jetpack over the top of it |
| `zarch` | 195,482 / **208,206** / 215,619 | 25 | Zarch's ground: a chequered plane, turning |
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

And moving memory about, measured on the eight-line scroll (`scroll8`):

| | T-states a byte | |
|---|---|---|
| cleared by `PUSH` | **7.33** | the interrupt let in every 232 T-states |
| cleared by `LD (HL),A` / `INC HL` | 13.25 | |
| copied by `LDI`, unrolled 64 | **16.16** | and `SP` never touched, so no `DI` |
| copied through the stack, eight bytes a block | 20.24 | 18.86 with the interrupt left alone; 11.5 of it is the `POP` and the `PUSH` |
| a DI window, `LD SP,IY` / `EI` / `NOP` / `DI` | 22 a window | 7.3% of the move, for 53.7 µs of latency |

| whole routines | T-states | |
|---|---|---|
| `sc_scroll` — 24K screen up eight lines, all stack | 484,155 | 4.0 frames at 50 Hz |
| `sc_scrolli` — the same, `LDI` for the move | **388,062** | 3.2 frames |

## 1b. Sound

| | T-states | |
|---|---|---|
| `crow_frame`, cawing (`crow`) | **1,654** | twelve SAA1099 registers, 1.4% of a 50 Hz frame |
| `crow_frame`, silent | 55 | |
| `crow_frame`, starting a caw | 784 | the LFSR that varies each call |
| `crow_init` | 1,419 | sixteen registers, once |
| `sk_frame`, a note going (`shaku`) | **1,554** | a shakuhachi: f, 2f, 4f and a breath channel |
| `sk_frame`, a note starting | 1,990 | the octave registers as well |
| `st_frame`, holding a chord (`strings`) | **1,097** | six channels: a triad and a detuned copy of it |
| `st_frame`, at its busiest | 2,463 | a chord change |
| `en_frame` (`ensemble`) | **3,360** | both of them at once, three oscillators each |
| `sm_frame` (`storm`) | **3,153** | distant thunder and rain, two noise generators, no tones at all |

All verified the same way as everything else - every OUT, in order,
against the routine's model - and then played through
`tests/saa1099.py` to make the wavs in `demo/`. See `crow.md`,
`shaku.md`, `strings.md` and `ensemble.md`.

A whole arrangement driven from a register log costs less than any of
them, because most frames change nothing. Over 9,898 frames of a 197 s
recording reduced to six channels by `chiparr.py`, at the measured **74
T-states** a (register, value) pair from `saa.z80s`:

| | pairs a frame | T-states |
|---|---|---|
| mean | 2.86 | 212 — 0.18% of a 120,000 T-state frame |
| median | 2 | 148 |
| worst frame | 31 | 2,294 — 1.9% |

See `chiparr.md`; `arrange.md` is the other way of doing it, an order of
magnitude above this because it rewrites every channel every frame.

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
| **A whole-screen copy through the stack** (`scroll8`) | 476,645 T-states for the 23,552 bytes an eight-line scroll moves, against 380,552 by unrolled `LDI` | `POP`/`PUSH` moves a byte in 11.5 T-states against `LDI`'s 16 and still loses: eight bytes is all the register there is, and the two `LD SP`s round them are 58 more. `LDI` also never touches `SP`, so it needs no `DI` at all. The clear underneath goes the other way — 7,510 against 13,567 — because there the source is a register |
| **Split prismpre's erase box** — one for the sigma, one for the triangle | blanks 94% of the bytes one box does; a box a piece blanks 115% | the pieces' boxes overlap too much |
| **Drop the lighting from prism** (flat faces, visibility kept) | 446,602 → **410,789**, 14.6 Hz | `pr_light` 73,704 → 37,891; the other half *is* the visibility test. prism's non-drawing work is 213,320 even with no lighting at all — 89% of the whole 25 Hz budget — so no lighting setting reaches 25 Hz |
| **Autocorrelation for the bass line** (`transcribe.py`), global argmax | read a 197 s recording's bass as F1 for nearly its whole length, through a progression that moves | a periodic signal correlates as well at 2T as at T, so the peak is an octave out as often as not |
| **The same, taking the shortest lag within 85% of the best** | read a 73.4 Hz saw as D3 (+1200 cents) and the recording an octave above its real line | it takes the half-period peak instead; no tie-break on lag length fixes both directions. Replaced by a 16,384-sample harmonic sum plus an odd-harmonic octave test, which reads the saw at 73.4 Hz exactly — see `chiparr.md` |
| **Band energy to classify a drum hit** | every one of a cue's 16 metal hits came out "hat" | a sustained hi-hat contributes to the high band whether or not it is part of this hit, and a band three octaves wide sums more bins than one an octave wide. It is the per-bin *rise* at the onset that is the hit |
| **Chord quality decided per window** | a D minor cue's first two bars came out D major, and the arpeggio played F# against them | those bars contain no third at all. Each root now takes the quality the whole piece's evidence gives it, weighted by duration |
| **Letting the parts yield to each other** (`chiparr.py` v1) — the arpeggio resting under the lead, a channel each for the drums, the lead doubling itself | 37.6% of the source's strong 200-2500 Hz peaks covered, 2 to 3 tone voices a frame | the lead sounds for 80% of the recording, so "rest under the lead" means "do not play", and the mid register is then empty. Nothing yields now: 57.8% covered, 4.45 voices a frame, for 1.2 more register pairs a frame |
| **A silent state in the lead tracker's Viterbi** (`transcribe.py`) | the lead leapt more than a seventh on 122 of its 371 intervals - A4 C5 E5 A4 C5 C6 F5 A4 ... D6 B4 D5 | re-entry from silence carried no pitch penalty, so silence was a free teleport between registers - and at 2.0 a semitone, twice the most any frame can pay, teleporting was the only way the path could move. No silent state now: the path is continuous, steps capped at 7 semitones, penalty 0.3, voicing decided afterwards from the salience along the chosen path. 122 leaps became 43 after folding |
| **The lead at level 12 under a bass at 13** (`chiparr.py`) | reported as "the lead mostly vanishes" at 25 s, where it measurably sounds in 100% of frames with the best peak coverage in the recording | a lead that is not the loudest voice is a lead the listener reports as missing while it plays. Lead 15, bass 12, inner voices 7 and 5: loudest in 96% of its frames, 4.8 dB clear |
| **A lagging reference for the octave fold** | turned 2 leaps into 3 on the test cue | the reference drags behind a melody that is climbing and then folds a later note back down, inventing a leap. A centred median over four notes either side leaves the cue untouched and still takes the real recording from 122 to 43 |
| **`decay` running to zero** | the bass sounded in 63% of frames where the score had it in 89% | a 105-frame note at 0.12 a frame runs out of level before it runs out of note. A floor at 55% of the attack fixed it and *reduced* the register writes, because a level that stops changing stops being written |
| **An FFT's own bins as bass pitch candidates** (`transcribe.py`) | a measured B1 came back as A#1 on every frame it sounded | at 16,384 samples a bin is 2.7 Hz - a sixth of a semitone at 300 Hz but four fifths of one at 58 Hz, so the candidate set cannot name the note. A logarithmic grid at 15 cents took a second recording's bass from 6 of 20 seconds right on pitch class to 10 of 20 |
| **Tracking the bass without knowing where the kicks are** | with eighth-note kicks, the bass came back alternating E1 with a different note every time - the bass and the kick taking turns | a kick is a pitch too, 40 to 60 Hz of it. Drums are found first now and the bass is blanked for five frames at each kick: leaps wider than a seventh fell from 189 of 841 to 43 of 820 |
| **An onset threshold against the global peak flux, and a 40-140 Hz low band** | 2.81 hits a beat, 862 classified kick against 86 snares and 7 hats | the band contains a bass note's fundamental so every bass attack reads as a kick, and a global threshold passes almost every ripple on a track with even dynamics. 40-90 Hz, a kick must out-rise the mid band by half again, and the threshold is the local median flux |
| **A fixed five-frame kick steal of the bass channel** | at two kicks a beat, 30% of the track has no bass at all | the steal is capped at the gap to the next kick now: an accent, not a hole |
| **A 40 Hz floor on the bass candidates** | the test cue's sub at D1 (36.7 Hz) sat below it, so the octave search piled up against the bottom edge and reported E1 - two semitones wrong | the floor is 36 Hz |
| **Assigning the extra voices by continuity** rather than by register | voice 0 ran E4 - E5 - C5 - C4 - A3 inside ten seconds, and two voices landed on A3 together | subtracting a claimed note's harmonic comb does not stop a candidate 40 cents away reclaiming it. A register each cannot cross and cannot duplicate |
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
