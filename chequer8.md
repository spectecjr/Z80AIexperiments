# chequer8.z80s — design notes

**The board, a two layer desert on the horizon, and the pilot — every pixel
of it drawn from scratch, every frame.** 189,528 T-states, **79% of a 25 Hz
frame**, and 212,911 in the worst frame found by sweeping cameras, layer
offsets and poses.

| | T-states a frame | |
|---|---|---|
| `chq4_floor` + `chq4_msk8` (chequer5's paged board, unchanged) | 113,375 | |
| **the desert** | **61,576** | 24 scanlines, two layers, by pixels |
| **the pilot** | **14,479** | all 96 rows of him, compiled |
| the paging and the flip | ~100 | |
| **`c8_frame`** | **180,981 / 189,528 / 210,166** | **25 Hz** |

Bit exact against `tests/chequer8.py` over 260 camera positions, which is a
whole period of both layers and every pose.

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

**The front layer is spans**, because the rear layer has to show between its
dunes. It is a heightfield — one dune top a pixel column — which gives per
row the runs where the dune has already started and the runs where it starts
on this very row and is lit. The Z80 subtracts the offset, splits whatever
crosses the screen's edge, and draws each span with `PUSH`es down the middle
and a read-modify-write at either end where the edge lands inside a byte.

| | T-states a frame | |
|---|---|---|
| the rear layer | 34,856 | 24 rows, of which about a third is spill |
| the front layer | 26,656 | 32 spans over 860 pixels |
| **`c9_band`** | **61,511** | **56,130 to 80,880 over a whole period** |

## This is where a 256K SAM runs out

The map is now:

    0,1  2,3  4,5      the board's run bank, cut by band
    6,7  8,9           its swap mask tables, 512 of them
    10,11  12,13       the two buffers, each with the resident code in
                       the 8K a MODE 4 screen leaves at the end of its
                       odd page
    14,15              the pilot, compiled
    16,17  18,19       the desert's rear layer, cut by row

Twenty pages. A 256K machine has sixteen, and chequer7 used every one of
them. `LMPR` addresses 32, so this wants a **512K SAM** — and that is a
decision, not an accident, so here is what a 256K version would have to give
up: the desert at two pixel phases rather than four (22K rather than 45K,
and an odd byte to put back at the end of each row), and four rows off the
band. It would fit, and it would be uglier in exactly one place: the row
where the odd byte lands.

## Invariants

- The order is board, desert, pilot. The board never touches rows 73..96
  and the desert never touches row 97, so the only ordering that matters is
  the pilot's, and he is over both.
- **Every `CALL` must be made with the page its return address is in still
  mapped.** `c9_band` pages the rear layer's chunks in and cannot `CALL`
  while they are there; that is why the chunk switch is inlined twice
  rather than being a subroutine, and why `c9_band` puts the board's bank
  back before it returns.
- The band is drawn **bottom upwards**, because that is what makes the rear
  layer's spill land in the row that is drawn next.
- `SP` is the screen for the whole band, so the front layer's own `CALL`s
  want it put back first — the spill repair leaves it in the screen.
- Both layers' periods are 256 pixels, the width of the screen, so the wrap
  is what the subtraction does on its own.
- The desert's colours are the pilot's — 4, 5, 6, 7 and 12 — because those
  are fixed; the copper grades 1, 2 and 3, and the band's sky is index 1 so
  that it grades with the rest of the sky.
- `c9_far`, `c9_near` and `c8_pose` all come from the caller every frame,
  like the camera. There is a copy of the resident block behind each buffer
  and nothing in it may carry state.

## What is left

- **The rear layer's spill is a third of it.** A run entered at *s* makes
  `128 - s` pushes and only 64 of them land: 8,448 T-states a frame on
  average and 16,896 in the worst. Writing a `JP` over the stop point and
  putting the three bytes back afterwards would cost about 140 a row rather
  than 352, for a stop address a (row, phase, entry) — 12K more of bank.
- **`c9_span` costs 833 T-states a span** and only 430 of its bytes are
  pixels. It passes half its state through memory because it was written to
  be read; registers and a tighter split of the two ends should halve it.
- **The board is 60% of the frame and has not been touched since
  chequer5.** Everything above has moved on; `chq4_msk8`'s four pages of
  lookup are the next thing to look at.

    python3 tests/desert.py /tmp/desert.png   # look at the layers, 3x
    python3 tests/mkdesertdata.py             # regenerate the rear layer
    python3 tests/mkjetrun.py                 # and the compiled pilot
    python3 tests/test_chequer8.py            # verify against the model
