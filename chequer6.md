# chequer6.z80s — design notes

**chequer5's board with a pilot standing in front of it.** 32×96 pixels of
person in a jetpack, back to us, in the middle of the screen and over the
top of everything — **three poses, banking left, level and right**, with a
mask, for **33,452 T-states a frame**. The whole thing is 143,643, still
60% of a 25 Hz frame.

| | T-states a frame | |
|---|---|---|
| `chq4_floor` + `chq4_msk8` (chequer5's paged board, unchanged) | 110,191 | |
| **the pilot** | **33,452** | 47 scanlines of him |
| **`chq6_frame`** | **143,643 steady** | **25 Hz, 60% of the frame** |
| a frame that changes pose | 159,388 | the top half, once a buffer |

Bit exact against its model over 112 camera positions, poses and all. The
board is chequer4's routine over chequer5's viewport, not a line of it
changed: everything here is the sprite.

## What the paged bank bought it

The first version of this file ends with *"36 bytes spare below 0x2000 and
109 in the gap — this is the last thing that fits"*. The board's bank is in
pages of its own now (`chequer5.md`), so the pilot has the whole 8K a MODE
4 screen leaves spare, and two things it could not afford before:

**A mask.** A byte with one of its two pixels covered is read, masked and
written rather than stored — three times the work — so the odd pixel used
to go to the pilot's own black outline instead, thickening it to two pixels
here and there. There are 110 such bytes in the sprite, they are two ops a
row, and the outline is one pixel wide everywhere now. It costs about 7,900
T-states a frame, which is most of the difference between 25,528 and
33,452.

**Three poses.** A shear rather than three sets of profiles — three pixels
at the helmet, tapering to none at the knees — and 675 bytes of stream and
4,400 of compiled run for the lot. The top half is still drawn once per buffer, and **each
buffer's copy of the code remembers which pose its top half has**, which is
free: the paged map keeps a copy of the resident block behind each buffer,
so a per-buffer byte is what you get whether you want one or not. Changing
pose costs one top half in each buffer and nothing after that.

## The top half is a run, not a stream

Nothing paints over rows 48..96, which means two things and the second one
is the useful one: the pose that was there has to be cleared, and **the
background up there is one constant** — this viewport has no haze, so it is
sky all the way to row 96.

So the top half is not played at all. It is a compiled run of `PUSH`es with
the sky baked into the transparent bytes *and* into the single pixel ones,
which makes it 5.5 T-states a byte with no mask and no clear: the run
covers the whole 16 byte box, so whatever pose was there goes under it.
**7,880 T-states for 49 rows**, against a stream and a clear that were
about 41,000 between them, and a frame that changes pose went from 200,875
to 159,388.

It is 1,486 bytes a pose where the stream was about 400, and worth it three
times over: that is paid in the 8K behind the screen, where there is now
room, and what it buys back is paid in the frame.

## Three things make him cheap

**Half of him is never redrawn.** The pilot stands on rows 48 to 143 and
the board only draws from row 97 down, so rows 48..96 go into each buffer
once and are not touched again until the pose changes — nothing else
writes there, not even the top run's spill, which lands in the last four
bytes of row 96. Only the 47 rows the board draws over are redrawn a frame:
220 bytes of stream rather than 565.

**Most of him is whole bytes.** A sprite byte is two pixels, and the 902
bytes of him that are fully covered are `LDIR` all the way; only the 110
where the silhouette does not land on a byte are read, masked and written.
That is two ops a row, not two hundred.

**Two thirds of his rows repeat the one above.** A person 32 pixels wide
does not change much from row to row, so the 47 rows the board draws over
come out as **15 rows of stream**, each with a repeat count, and the player
runs a row's ops again rather than storing them again. (The top half gets
nothing from this, being a straight run now: a repeat there is eight more
`PUSH`es and a `LD SP`.)

## The stream

One entry a row, played by `chq6_draw`. This is the **lower** half only —
the rows the board draws over, where the background moves and so has to be
masked against:

| | |
|---|---|
| `rep` | how many scanlines these ops draw. `0` ends the stream; `0xFF lo hi` says the stream goes on at another address |
| `0x01..0x10` | skip n bytes |
| `0x20+n` | copy the n bytes that follow |
| `0x40+n` | fill n bytes with the byte that follows |
| `0x60`, `0x61` | one pixel of the next byte is the pilot's — `0x60` its left, `0x61` its right — and the board keeps the other |
| `0x00` | end of row |

The jump op is there because the free memory is in pieces: the board's run
bank has taken all but 250-odd bytes either side of the screen, so the
player itself lives in the gap under 0x100 that the harness leaves and the
stream lives below the buffers with the board's tables. **36 bytes spare
below 0x2000 and 109 in the gap** — this is the last thing that fits.

Room for the stream came from `chq4_msk` — the swap mask a scanline, which
was 192 bytes indexed by row when the board only ever has 95 rows. It is
indexed from the top row now, like `chq4_ztab`, and costs nothing.

## The pilot himself

`tests/jetpack.py` draws him out of profiles — a list of (row, left, right)
that the rows between interpolate — because that is the only way to put a
person into a 32 pixel grid and still be able to move a shoulder by two
pixels afterwards. Eleven colours, all of them fixed: a SAM colour is two
bits a gun and a bright bit the three of them share, so the palette uses
triples that are all even or all odd, which are the ones that survive the
trip through `mkchqdata.sam` unchanged. The board's stripes still own
indices 1 and 2, and nothing the copper does touches the pilot's.

Straight edges are worth data here: an arm that tapers by a pixel every
five rows is five rows the stream cannot share, so the arms and legs taper
in two steps rather than five. That alone was 58 bytes, which is the
difference between fitting and not.

## Invariants

- The pilot is drawn after the board and before the flip, or the board
  draws over him.
- Rows 48..96 are drawn once per buffer **per pose**, as a compiled run
  with the sky baked in. If anything else ever writes there — a horizon, a
  city, a score — they have to be redrawn every frame, the sky stops being
  a constant, and the run has to go back to being a masked stream.
  `chequer7` is that demo: a city on rows 81..96, the division moved up to
  row 81, and 63 rows of stream a frame rather than 47.
- `chq6_seen` is per buffer and must stay in the resident block, which is
  the one thing the paged map duplicates. Nothing else here may carry
  state from frame to frame.
- The stream's row entries are what the split at row 97 is cut on, so a
  repeat run may not straddle it. `tests/mkjetdata.py` cuts it there.
- 16 bytes wide starting at byte 56 of a row never crosses a page, which is
  why `skip` is one `ADD A,E`.

`CHQ6_CITY`, which the harness sets, puts chequer7's band of city in
between the board and the pilot; everything else about the routine is the
same, including where the pilot divides, which comes from the data.

    python3 tests/jetpack.py /tmp/pilot.png   # look at him, 8x
    python3 tests/mkjetdata.py                # regenerate the stream
    python3 tests/test_chequer6.py            # verify against the model
