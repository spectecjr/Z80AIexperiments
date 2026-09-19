# Could this be a playable Space Harrier?

**Yes, at 16.7 Hz — three display frames — with the board brought down to
about 70 scanlines and the horizon band shortened, and with the sprite load
at about two thirds of what was asked. The full ask is a 12.5 Hz game.**
The arithmetic is in `tests/mkbudget.py` and `reports/budget.txt`;
everything below is measured except where it says otherwise.

**In the currency that binds**, which is memory slots rather than T-states
— see the last section, which is no longer a list of caveats:

| | slots | frames | |
|---|---|---|---|
| the picture without sprites | 33,888 | 1.42 | board at 70 rows, a 12 row band, the pilot, sound, the game's arithmetic |
| **the ask: 4 large, 8 medium** | **91,233** | **3.83** | **12.5 Hz** |
| **2 large, 4 medium, 6 small** | **71,224** | **2.99** | **16.7 Hz, with nothing to spare** |
| 1 large, 5 medium, 6 small | 69,883 | 2.94 | 16.7 Hz |

A display frame is 23,808 slots.

| the ask: 12 sprites, 4 of them 32x135 | T-states | |
|---|---|---|
| the sprites | 226,500 | 15,012 bytes drawn, over the board |
| the board at 70 rows, a 12 row band, the pilot, sound, the game's own arithmetic | 128,097 | |
| **a frame** | **354,597** | **148% of 25 Hz, 98% of 16.7 Hz, 74% of 12.5 Hz** |

| a realistic one: 2 large, 4 medium, 6 small | T-states | |
|---|---|---|
| the sprites | 170,070 | 9,774 bytes drawn |
| everything else, as above | 128,097 | |
| **a frame** | **298,167** | **124% of 25 Hz, 83% of 16.7 Hz, 62% of 12.5 Hz** |

The T-state tables that follow are what the code costs uncontended. On the
real machine it is **34% more**, consistently, and that is measured rather
than guessed now — the section at the end says how.

**These sprite figures are the masked form**, at 13 T-states a byte drawn,
because that is what chequer10's trees are. `mipsprite.md` measures the
other form of the same thing — an opaque box, which is what the section on
sprites against the sky below argues for — at **8.8 T-states a byte**, and
a z-bucket scheme that gets fifteen sprites over a 3:1 depth range into
**77,129 T-states**. A game built that way rather than this one's way has
appreciably more room than the tables above suggest: the ask is heavy
*because it is masked and tall*, not because twelve sprites is a lot.

## The currency is bytes written

A MODE 4 screen is 24,576 bytes. A 25 Hz frame is 240,000 T-states, and
the board writes its bytes at a measured 9.5 T-states each. **So a 25 Hz
frame can write the screen about once**, and every argument below is about
which bytes.

| | T-states a byte | |
|---|---|---|
| `PUSH DE`, the floor | **5.5** | nothing on a Z80 is faster |
| a compiled sprite, solid, 32 x 48 | 6.3 | the floor plus a step a row |
| the same, 16 x 135 | 7.2 | taller is dearer: more steps |
| the board | 9.5 | the floor plus a square boundary every few bytes |
| a compiled sprite, masked, 70% filled | 13 … 18 | edges are read-modify-write, air is jumped over |
| a small masked sprite, 10 x 54 | 25 | seven bytes a row, two of them edges |
| the desert's band | **19.5** | pixel-precise spans, the dearest picture on the screen |

**A sprite's cost is its shape, not its size.** Wide and short beats tall
and narrow, because every row costs a `LD HL,-d / ADD HL,SP / LD SP,HL`;
solid beats masked by 2 to 3 times; and a flat colour beats a textured one
— the tree's speckle alone costs **17%** of its draw, and its black
outline another 8%.

## The board is 1,213 T-states a scanline, wherever it is

Measured at every horizon it can have, and it is nearly flat: 1,213
T-states a row at 96 rows, 1,247 at 70, 1,426 at 19. It has to be — a
shallow board is the deep one with rows left out, so each row drawn is an
average row rather than a cheap one.

**Which makes the horizon a straight lever.** Every scanline of board you
give up is 1,213 T-states back:

| the board | T-states |
|---|---|
| 96 rows, half the screen | 116,448 |
| 70 rows | 87,299 |
| 48 rows | 62,339 |

Space Harrier's own horizon sits at about 40% of the playfield, which on a
176 row playfield is 70 rows. **That is 29,000 T-states of the difference
between 25 Hz and 16.7 Hz, for free, and it is what the arcade looks
like.**

## The horizon band is the worst value on the screen

49,866 T-states for 20 scanlines — **2,493 a row, twice the board's** —
because the front layer scrolls at pixel precision and its spans do not
land on byte boundaries. `chequer8.md` took that decision on purpose: the
parallax is the point of it.

A game does not need it at that price. Forcing the front layer's offset
even makes every span whole bytes and the notes already cost that at about
5,000 T-states; cutting the band from 20 rows to 12 takes it to about
18,000 all in. **32,000 T-states for something almost nobody looks at.**

## Sprites over the board are free to erase; sprites over the sky are not

The board repaints every byte under it, so a sprite standing on the ground
costs its draw and nothing else. A sprite against the sky has to have its
old box put back, because the sky is painted once:

| 16 x 135, against the sky | T-states |
|---|---|
| masked draw + wipe of the old box | 26,615 + 15,120 = **41,735** |
| the box drawn solid, twice over | **31,036** |

**Which is the surprise: against a flat background, drawing the whole box
opaque is cheaper than masking it.** Masked drawing costs 13 to 18
T-states a byte *drawn* and skips the air; a solid `PUSH` box costs 7.2 a
byte of *box* and does not care. Below about 75% fill the solid box wins
outright, and it wins twice over if it also saves the wipe.

So: **keep the action on the ground plane**, which is what Space Harrier
does anyway, and compile an over-the-sky variant of the few sprites that
fly. Every sprite over the board rather than the sky is 7,000 to 15,000
T-states.

## The score and lives pay for themselves twenty times over

A 16 row black strip at the top is **16 rows the playfield no longer
has**, which is 19,400 T-states of board and band that never gets drawn.
What goes in it:

| | T-states |
|---|---|
| a digit, 8x8, drawn opaque with its own black background | ~230 |
| all fifteen digits — six of score, six of high score, three of lives | ~3,450 |
| the one digit that changed | ~230 |

So there is no need for the one-digit-a-frame trick: **redrawing the whole
status line every frame is 1.4% of a frame** and drawn opaque it needs no
wipe at all. Note that the *hardware* border cannot hold pixels — it is
one colour out of port 254 — so a "border" here means scanlines of the
screen, and those scanlines are exactly what makes the strip free.

## What else a game needs, and it is not much

| | T-states | |
|---|---|---|
| twelve objects: integrate, project, pick a size, sort by depth | ~3,000 | the divide is a reciprocal table, as the board's already is |
| collisions, twelve boxes against the player | ~750 | |
| input, one port | ~200 | |
| spawning and the level script | ~500 | |
| **music and effects** | **2,242** | measured — `sound.md` |
| the frame's own overhead: the horizon table, the mask gather, the flip | ~7,500 | measured |

**About 14,000 T-states, which is 6% of a 25 Hz frame.** The game is not
the problem. The picture is the problem.

## Memory: not the binding constraint, but only just

A compiled sprite costs about **2.75 bytes of code a byte of picture** —
measured on the tree, whose eight sizes are 3,773 bytes of picture and
10,384 bytes of code. A solid object of the same box is more, because
there is no air to skip: call it 13,000 to 17,000 bytes for an object at
eight sizes.

`LMPR` addresses 32 pages, so 512K is the ceiling for this paging scheme,
and chequer10 already uses 26 of them. What a game can get back:

| | pages |
|---|---|
| the swap masks, recomputed per scanline instead of stored | **4** |
| the board bank at 64 pixel squares rather than 80 (chequer8's 2,080 bodies, not 3,240) | **4** |
| the desert's rear layer, cut to a 12 row band | **2** |
| free already | 6 |
| **for sprites** | **16 pages, 256K** |

Which is **fifteen to twenty object types at eight sizes each** — more
than Space Harrier has. Recomputing the masks costs 1,500 to 7,800
T-states a frame (`chequer9.md` measures both), which at 16.7 Hz is
affordable and buys a quarter of the sprite bank.

If it is still not enough: **page the sprites per level**, which is what
the arcade's ROM banking did. A level uses four to six object types.

## Contention: no longer a guess, and it costs a third

Every T-state figure in this repository is raw Z80 time. The machine does
not work that way. **The ASIC shares one memory bus between the CPU and the
display and grants the CPU one access per 8 T-states while the raster is in
the display window, one per 4 T everywhere else** — 23,808 slots a frame,
derived in `bubble/tools/budget.py` and set out in
`docs/BUBBLE_BOBBLE_SAM.md`. Every access costs a slot: an opcode fetch, an
operand byte, a data read, a data write, each half of a `PUSH`. The cost of
an instruction is `max(natural_T, accesses x slot_width)`.

**So the question is not how many T-states a frame takes but how many
accesses**, and `tests/sam.py`'s `traffic()` counts those. Put the two
together — which no single branch of this repository had done — and the
answer falls out:

| a chequer10 frame | T-states | accesses | by T | by slots | |
|---|---|---|---|---|---|
| the tallest board, three trees | 218,520 | 57,994 | 1.82 | **2.44** | +34% |
| the tallest board, no trees | 187,261 | 49,903 | 1.56 | **2.10** | +34% |
| the shortest board, no trees | 92,526 | 24,217 | 0.77 | **1.02** | +32% |

This code is slot-limited — 3.7 T-states an access against a frame that
averages 5.0 — so the right hand column is the true one. **chequer10 at its
worst needs three display frames, not two**: 16.7 Hz on the real machine
where the emulator says 25.

**And a compiled sprite costs far more in slots than in T-states**, because
the code stream is memory traffic too:

| the tree | T a byte drawn | slots a byte drawn |
|---|---|---|
| 32x135 | 14.5 | **3.82** |
| 20x81 | 17.8 | 4.61 |
| 8x27 | 27.8 | 6.84 |
| a `PUSH` fill, which cannot draw a picture | 5.5 | **1.50** |

Compiling the picture into code buys a factor of three or four in T-states
and less than two in slots, because every instruction of it has to be
fetched through the same bus as the pixels it writes. It still wins — a
data-driven blitter reads a source byte, a mask byte and the destination
before it writes, which is four slots a byte before any loop overhead — but
not by the margin the T-state tables suggest.

That makes the recommendation:

- **Design to 16.7 Hz**, three display frames, and a sprite budget of
  **about 9,500 bytes a frame** — two large, four medium, six small, which
  is 2.99 frames of slots and therefore has nothing in hand.
- **A 176 row playfield** under a 16 row status strip, the horizon at
  about 70 rows of it.
- **A byte-aligned horizon band**, twelve rows.
- **Keep the sprites on the ground**, and compile solid-box variants of
  the ones that fly.
- **Draw them as opaque boxes off a width chain**, per `mipsprite.md`, not
  as masked silhouettes at eight fixed sizes: 8.8 T-states a byte rather
  than 13 to 18, and the heights come free off a row program.
- And **confirm the slot rates on real hardware**. The 1-per-8-T display
  grant is a model, stated in `docs/BUBBLE_BOBBLE_SAM.md` and not yet
  checked against a machine; everything above hangs off it, and a rate of
  1-per-6 or 1-per-12 moves every verdict here by a frame.

    python3 tests/mkbudget.py                 # every number above
