# chequer8.z80s — design notes

**The board over a viewport of its own, a two layer desert standing on it,
and the pilot — every pixel drawn from scratch, every frame.** 189,719
T-states, **79% of a 25 Hz frame**, and 197,353 in the worst frame found by
sweeping cameras, layer offsets and poses.

| | T-states a frame | |
|---|---|---|
| `chq4_floor` + `chq4_msk8` | 95,640 | 77 scanlines: the bottom 40% |
| **the desert** | **79,552** | 32 scanlines, two layers, by pixels |
| **the pilot** | **14,401** | all 96 rows of him, compiled |
| the paging and the flip | ~130 | |
| **`c8_frame`** | **184,510 / 189,719 / 196,105** | **25 Hz** |

Bit exact against `tests/chequer8.py` over 260 camera positions, which is a
whole period of both layers and every pose.

## The board gets the bottom 40%, and a camera of its own

chequer5's camera puts the horizon at row 96, so its board is half the
screen. chequer8 wants the bottom 40% — more sky for the desert to stand in
— and gets it by moving the camera rather than by cutting the board short:

    the horizon    row 114 rather than 96, so 77 scanlines of board
    the camera     308 world units up rather than 380, which keeps a
                   square 64 pixels wide at the bottom of the screen

The board still runs all the way down to one pixel squares; it is the same
picture, steeper. Nothing in the routine changed — `tests/harrier.py` takes
the viewport from the environment now, and `tests/mkchq8data.py` runs the
same generators over it to produce a set of tables of its own. A run is a
function of a square's width and nothing else, so the runs are the same
runs; what comes out different is the bands, the compiled bodies, the swap
masks and the viewport constants.

It is also **17,000 T-states cheaper**: 94,260 against 111,707, because
eighteen scanlines of board went away and the ones that went were near the
horizon, where the squares are narrow and the bands change every row.

## Nothing is drawn once per buffer any more

chequer6 and chequer7 draw the pilot's upper rows once into each buffer,
because nothing paints over them; that is what makes a pose change cost a
whole extra sprite, and what made the city's arrival move the division
between his halves. chequer8 drops the idea entirely. Everything on the
screen is redrawn every frame, so:

- a pose can change on any frame for nothing;
- the background can move under him anywhere, at any rate;
- there is no per-buffer state left in the resident block at all, which
  means nothing to keep in step and nothing to clear.

It costs the pilot's top half — and the compiled pilot pays for that many
times over.

## The pilot is code now, in a page of his own

**All 96 rows in 14,479 T-states**, where chequer7 plays 63 rows from a
stream for 46,793. The stream player spends about 63 T-states on every byte
it puts down: an op to dispatch, a count to unpack, an `LDIR` or a `DJNZ`.
None of that is a decision about *this* frame, so `tests/mkjetrun.py` takes
it when the data is made:

| | |
|---|---|
| a run of solid bytes | `LD SP,end` and a `PUSH` a pair — 5.5 T-states a byte, with `DE` reloaded only where the pair changes and `SP` only where a run does not carry on from the one before |
| an odd byte | `LD A,n / LD (nn),A`, because `PUSH` writes two |
| one pixel of pilot | `LD A,(nn) / AND / OR / LD (nn),A` — the only read-modify-write left, 110 bytes of him |

Every address in it is absolute, which is only possible because the paged
map puts **the back buffer at 0x8000 whichever buffer it is**.

At about four bytes a pixel byte the three poses come to **8,688 bytes**,
which does not fit in the 8K behind the screen. So they have a page: `LMPR`
maps it over the board's bank for the length of the call, the poses are
reached through a table at the foot of the page the way the bank's chunks
are, and the bank goes back afterwards — **the caller's stack is in chunk
0, and that is the one thing the whole map has to respect.**

The division does survive in the data, but only there: above the band there
is nothing but sky, so up there the sky is baked into the transparent bytes
and the single pixel ones and the box is `PUSH`es with no mask.

## The desert scrolls by pixels, which is the whole point

The city in chequer7 moved by whole bytes — two pixels at a time, at 50 and
100 pixels a second — and read as scenery on rails. This moves the rear
layer **one pixel every three frames** and the front **one pixel a frame**:
8 and 25 pixels a second, and the ratio is what the eye reads as distance.

**What is in each layer is the other half of it.** The rear layer has the
great pyramid, a dune field, palms and a scatter of rocks; the front has
three smaller pyramids standing nearer — smaller, and in front, which is
what makes them pass across the great one. Something crossing in front of
something else at a different rate is the one depth cue that needs neither
colour nor perspective, and it is the reason the front layer cannot be a
compiled run: it has to leave the layer behind it showing.

A pixel is half a MODE 4 byte, and that is what it costs.

**The rear layer is compiled, one run of `PUSH`es a (row, phase).** A run
holds two whole periods of its row, so entering it at the right pair gives
any rotation of the pattern; it then runs to its end, and the pushes left
over spill into the row above — which is drawn next, because the band is
drawn bottom upwards. Only the topmost row's spill has to be put back, and
above the band is sky. That is road2's window trick over a picture instead
of a road.

**Four phases, not two.** A run can be entered at a pair, which is four
pixels; `SP` could take up the odd byte, but then the row's last byte falls
outside the pairs and wants a store and a table of its own. Compiling the
pattern at all four pixel offsets removes that whole limb — the entry is
`64 - offset/4` and `SP` is always the row's right hand end — for twice the
memory, which is what a bank of pages is for.

**The rear layer is a picture, not a shape list**, and this is the part
worth keeping. It is drawn in `tests/desert.py` as pixels and compiled, so
detail costs *memory* and not time: the pyramids have a lit face and a
shadow face, there is a ridge that undulates, a stand of palms, a scatter of
rocks. The city was rectangles worked out at run time, and every one of
those would have been another rectangle a row.

**And it is stopped where it should stop.** A run entered at *s* has
`128 - s` pushes left in it and a row wants 64, so the rest used to spill
into the row above and be thrown away — 352 T-states a row on average and
704 in the worst frame. Each entry now carries the address of its own 64th
push, and the row loop writes a `JP` over the three bytes there and puts
them back afterwards: **144 T-states a row**, and the band's worst frame is
21,000 cheaper than its average used to be. A picture drawn out of compiled
runs has a flat cost now, which is what makes the rest of the frame
predictable.

**The front layer is spans**, because the rear layer has to show between and
behind its pyramids. Each row of a front pyramid is two runs, a lit face and
a shadow; the Z80 subtracts the offset, splits whatever crosses the screen's
edge, and draws each span with `PUSH`es down the middle and a
read-modify-write at either end where the edge lands inside a byte. **That
read-modify-write is the masking**, and it is the whole price of a layer
that is 1-pixel accurate and not opaque: about 45 T-states an edge, twice a
span.

| | T-states a frame | |
|---|---|---|
| the rear layer | 45,938 | 32 rows, and no spill left in it |
| the front layer | 33,614 | 57 spans, 590 T-states each |
| **`c9_band`** | **79,552** | **77,489 to 83,664 over a whole period** |

## This is where a 256K SAM runs out

The map is now:

    0,1  2,3  4,5      the board's run bank, cut by band
    6,7  8,9           its swap mask tables, 512 of them
    10,11  12,13       the two buffers, each with the resident code in
                       the 8K a MODE 4 screen leaves at the end of its
                       odd page
    14,15              the pilot, compiled
    16,17  18,19       the desert's rear layer, cut by row
    20,21              and the rest of it

Twenty-two pages. A 256K machine has sixteen, and chequer7 used every one of
them. `LMPR` addresses 32, so this wants a **512K SAM** — and that is a
decision, not an accident, so here is what a 256K version would have to give
up: the desert at two pixel phases rather than four (and an odd byte to put
back at the end of each row), and a shorter band. It would fit, and it would be uglier in exactly one place: the row
where the odd byte lands.

## Invariants

- The order is board, desert, pilot. The board never touches rows 83..114
  and the desert never touches row 115, so the only ordering that matters
  is the pilot's, and he is over both.
- **Every `CALL` must be made with the page its return address is in still
  mapped.** `c9_band` pages the rear layer's chunks in and cannot `CALL`
  while they are there; that is why the chunk switch is inlined twice
  rather than being a subroutine, and why `c9_band` puts the board's bank
  back before it returns.
- The band is drawn **bottom upwards**, which is what the rows are tabled
  in; nothing spills out of it now that the runs stop where they should.
- `SP` is the screen for the whole of the rear layer, so the front layer's
  own `CALL`s want it put back first.
- The three bytes a row loop writes over a run **must go back before the
  next row**, and they are kept in `B`, `C` and `A` because the run touches
  none of the three. `EXX` does touch `BC`, so the restore comes before it.
- Both layers' periods are 256 pixels, the width of the screen, so the wrap
  is what the subtraction does on its own.
- The desert's colours are the pilot's — 4, 5, 6, 7 and 12 — because those
  are fixed; the copper grades 1, 2 and 3, and the band's sky is index 1 so
  that it grades with the rest of the sky.
- `c9_far`, `c9_near` and `c8_pose` all come from the caller every frame,
  like the camera. There is a copy of the resident block behind each buffer
  and nothing in it may carry state.

## What a moving horizon would cost

The next thing this wants is a horizon that moves — the camera pitching as
the pilot climbs and dives. Most of what is here survives that, and it is
worth writing down which half does not, because the split is not obvious:

**These do not depend on the horizon at all.** A run is a function of a
square's width, and a compiled body is a function of a width and a phase —
neither knows what row it lands on. So the 78K of bank, which is the
expensive thing to build, is the same bank at every horizon. So is the
desert: its rows are its own picture, and `SP` puts them wherever the band
happens to be, so the band slides up and down the screen for nothing.

**These do.** The band table — how many scanlines each square width gets —
is 64 entries and would have to be built each frame or held one per horizon
step; it is small either way. `CHQ4_TOP` is baked into the code as fill
counts and `DUP` lengths, so those become entered-at-an-offset blocks, which
is what `road2` already does with its stale bands. And the swap masks are
the real bill: 512 tables of 128 bytes, indexed by depth, and the depth of a
scanline is exactly what a moving horizon changes. Either they are computed
per scanline again — 81 T-states a row, which is 6,200 for 77 rows and what
`chq4_msk8` did before it became a lookup — or there is a set per horizon
step, which there is not room for. The lookup was worth 6,100 T-states when
the horizon stood still; it is the first thing a moving one takes back.

## What is left

- **`c9_span` costs 590 T-states a span** and only about nine of its pixels
  are bytes. Tightening it once took it from 833; the rest of it is the
  caller's per-span arithmetic, which could be a table of (first byte,
  pairs, ends) computed once a frame rather than per span.
- **The board is half the frame** and has not been touched since chequer5
  beyond its viewport. 77 scanlines at 94,260 is 1,224 a row, where the row
  loop itself is about 600.
- **The sky is 43% of the screen and costs nothing**, which is a waste of a
  good frame: it is where a sun, a moon or a flight of birds would go for
  almost nothing, because anything up there is over a background that never
  moves.

    python3 tests/desert.py /tmp/desert.png   # look at the layers, 3x
    python3 tests/mkdesertdata.py             # regenerate the rear layer
    python3 tests/mkjetrun.py                 # and the compiled pilot
    python3 tests/test_chequer8.py            # verify against the model
