# chequer7.z80s — design notes

**chequer6, with a two layer city scrolling on the horizon.** Sixteen
scanlines between the board and the sky, holding two skylines that move at
different speeds — the far one a byte a frame, the near one two — for
**38,136 T-states a frame**. The whole picture, board and pilot and city,
is **201,281 T-states: 84% of a 25 Hz frame**, and 213,265 in the worst
frame found by sweeping cameras, city offsets and a pose change in every
single frame.

| | T-states a frame | |
|---|---|---|
| `chq4_floor` + `chq4_msk8` (chequer5's paged board, unchanged) | 113,375 | |
| **the city** | **38,124** | 16 scanlines, 2,048 bytes |
| the pilot, and the flip | 49,782 | 63 scanlines of him now, not 47 |
| **`chq6_frame`** | **193,921 / 201,281 / 209,572** | **25 Hz** |

Bit exact against `tests/chequer7.py` over 260 camera positions, which is
two whole periods of the far layer and four of the near one — every wrap of
every building, including the odd byte a wrap leaves behind.

## What the parallax is for

One scrolling skyline reads as wallpaper. Two, at a 2:1 speed ratio, read
as distance: the near buildings slide past the far ones and the eye gets
the depth cue it does not get from the colours, which at this size are
three greys. It is the cheapest depth in the demo — the board's is a
perspective divide a row, and this is a shift.

The layers scroll with the camera's **slide**, not its walk: eight world
units to the byte, so the eight second swing of `stroll()` moves the far
layer 160 pixels and the near one 320. A city on the horizon does not rush
towards you when you walk forwards, and one that does looks like a
backdrop on rails.

## The whole band is redrawn, every frame

There is no cleverness to be had about *what* changed: a horizontal scroll
changes every byte of every row. 2,048 bytes at the 5.5 T-states a byte
`PUSH` costs is 11,264, and the band measures 38,136, so the question is
where the other 27,000 goes. Each of these is the band measured over a
whole period of offsets with that layer's table emptied, not an estimate:

| | T-states a frame | |
|---|---|---|
| the sky | 13,247 | 1,024 pairs, the whole band |
| the far layer over it | 13,671 | 14 buildings |
| the near layer over those | 11,218 | 8 buildings, and a lit left face |
| **`c7_city`** | **38,136** | **36,130 to 41,159 over a whole period** |

**That is overdraw, and it is the cheap answer.** A byte under a near
building is written three times. The alternative is merging two interval
lists a row and drawing each span once — and the merge costs more on a Z80
than the 9,000 T-states of pixels it would save, because a span is 11
T-states a pair and a comparison is seven.

## Everything in it is a rectangle

A building is a run of whole bytes wide and a number of scanlines tall, so
drawing one is `SP` and a compiled block of `PUSH`es: **63 `PUSH DE` and a
`PUSH BC`, entered at 64 - pairs**. Three things fall out of that:

**The lit left face is free.** The last `PUSH` a run makes is the leftmost
pair it writes, so `PUSH BC` is the left face and `PUSH DE` is the body.
Make BC the same as DE and the rectangle is flat, which is what the sky and
the far layer want; make it lighter and the near layer gets a four pixel
highlight down its left hand side for nothing at all.

**The sky is a building.** One rectangle, 128 bytes by 16 rows, through the
same code.

**A row is 56 T-states of overhead on up to 704 of pixels.** The row
pointer, the 128 and the row counter live in the alternate register set,
because `BC` and `DE` are both colours and the fill block wants them where
they are: a row is `LD SP,HL / ADD HL,DE`, two `EXX` and a `JP (IX)`.

## What the parallax costs is one byte

A layer's period is the screen's width, which makes the wrap a mask — `u =
(x - offset) AND 127` — and cuts a building into one part or two. The far
layer moves **one** byte a frame, so the offset can be odd, so a part's
width can be odd. `PUSH` writes two bytes.

So a part of odd width has its left hand byte drawn as a column of single
stores, `LD (HL),A / ADD HL,DE / DJNZ` at 31 T-states a row. There are
**1.36 such columns a frame** on average, about 700 T-states, and every
width in the tables is even so that no building needs one until the
screen's edge cuts it.

## The setup was costing as much as the pixels

The first version drew every rectangle through one general routine that
worked out the address, the entry, the two colours and the split from
scratch: **800 T-states a building against 250 of pixels**, and the band
came to 46,212.

Only a building the screen's edge cuts can leave an odd width, need two
colours, or be in two parts. So the common case reads what it needs
straight out of the table — four bytes: the fill block's entry for its
width, and the address its top row ends at when the offset is zero — and
the general routine is left for the one building a layer that is cut. That
is 8 bytes a building of table and **7,454 T-states a frame**.

`IY` is the table pointer, so the fill block ends `JP c7_ret` rather than
`JP (IY)`, and `IX` is the entry: the fill block is `ALIGN 256` so that
`IXH` is set once a layer and an entry is `LD IXL,A`.

## The pilot has to be redrawn further up

chequer6 draws the pilot's rows 48..96 once per buffer, because nothing
else ever paints there. The city does, on rows 81..96, so **the division
moves up to the city's first row** and 63 scanlines of pilot are redrawn a
frame rather than 47. That is `tests/mkjetdata.py` emitting a second file,
`jetdata7.z80s`, cut at row 81 rather than 97; the player and the routine
are chequer6's, with `CHQ6_CITY` set.

It costs 13,000 T-states a frame, and it is what chequer6.md's invariants
say it would: *"if anything else ever writes there — a horizon, a city, a
score — they have to be redrawn every frame"*.

## And the top half stopped being a stream

Above the board there is nothing but sky, in this viewport all the way to
row 96. So the rows nothing paints over are not a stream at all: they are
**a compiled run of `PUSH`es with the sky baked into the transparent bytes
and into the single pixel ones** — no mask, no `LD (HL)`, and no clearing
of the pose that was there, because the run covers the whole box. 33 rows
in **5,272 T-states**, and chequer6's 49 rows in 7,880 where the stream and
its clear were about 41,000.

That is what took the worst frame of this demo from 238,664 — which is
inside a 25 Hz frame by 1,336 T-states, which is not inside it at all — to
213,265. chequer6 got it too: its pose change was 200,875 and is 159,388.

## Invariants

- The city is drawn **after** the board and **before** the pilot. The board
  never touches rows 81..96 and the city never touches row 97, so the only
  ordering that matters is the pilot's, and he is over both.
- Both layers' periods are the screen's width, so a layer is one copy of
  itself and the offset is a mask. Change that and the wrap stops being
  `AND 127`.
- Every building's width is even. An odd one would want its odd column
  every frame rather than only at the screen's edge.
- `c7_t` comes from the caller every frame, like the camera: nothing in the
  resident block may carry state from frame to frame, because there is a
  copy of it behind each buffer.
- The city's three colours are the pilot's — 8, 10 and 11 — because those
  are fixed: the copper grades 1, 2 and 3, and the band's sky is index 1
  and grades with the rest of the sky.
- `DI` is held across the whole band, `SP` being the screen. `c7_rows`
  saves and restores it, so a `CALL` still returns.

## What is left

- **Compile the pilot's lower half too.** 46,793 T-states of stream
  playback against about 13,000 of `LD (IX+d),n` — but the compiled form is
  4 bytes a pixel byte and three poses of it will not fit in the 8K behind
  the screen, so it wants a page of its own. It is the largest single
  saving left anywhere in this demo.
- **Compile the far layer and the sky together**, one run a (row, phase),
  entered at a stub for the byte offset the way road2's rows are: 27,000
  T-states become about 13,000, at 17K of bank and a generator.
- **Windows.** The band has 26,735 T-states of a 25 Hz frame spare, and a
  lit window is a nibble in a `PUSH`ed constant — but only for buildings
  drawn from compiled runs, which is the item above.

    python3 tests/city.py /tmp/city.png     # look at the skylines, 3x
    python3 tests/mkcitydata.py             # regenerate the tables
    python3 tests/test_chequer7.py          # verify against the model and time
