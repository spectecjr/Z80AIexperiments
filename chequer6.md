# chequer6.z80s — design notes

**chequer5's board with a pilot standing in front of it.** 32×96 pixels of
person in a jetpack, back to us, in the middle of the screen and over the
top of everything, for **25,528 T-states a frame** — which takes the whole
thing to 154,607, still 64% of a 25 Hz frame.

| | T-states a frame | |
|---|---|---|
| `chq4_floor` + `chq4_msk8` (chequer5's board, unchanged) | 128,587 | |
| **the pilot** | **25,528** | 47 scanlines of him |
| **`chq6_frame`** | **150,767 / 154,607 / 158,575** | **25 Hz, 64% of the frame** |

Bit exact against its model over 112 camera positions. The board is
chequer4's routine over chequer5's viewport, not a line of it changed:
everything here is the sprite.

## Three things make him cheap

**Half of him is never redrawn.** The pilot stands on rows 48 to 143 and
the board only draws from row 97 down, so rows 48..96 go into *both*
buffers once at `chq6_init` and are never touched again — nothing else
writes there, not even the top run's spill, which lands in the last four
bytes of row 96. Only the 47 rows the board draws over are redrawn a frame:
183 bytes of stream rather than 565.

**He has no mask.** A sprite byte is two pixels, and a byte with only one of
them covered needs a read, an AND, an OR and a write — three times the work
of a byte that is simply stored. So the silhouette is rounded out to whole
bytes by giving the odd pixel to the pilot's own black outline
(`tests/jetpack.py`). The outline is one pixel wide, so what that does is
thicken it to two pixels here and there, which is the cheapest possible
answer to an edge that does not land on a byte — and **every byte the pilot
draws is a whole byte**, `LDIR` all the way.

**Two thirds of his rows repeat the one above.** A person 32 pixels wide
does not change much from row to row: 96 scanlines come out as **43 rows of
stream**, each with a repeat count, and the player runs a row's ops again
rather than storing them again. 1,012 bytes of pilot become 565 bytes of
stream.

## The stream

One entry a row, played by `chq6_draw`:

| | |
|---|---|
| `rep` | how many scanlines these ops draw. `0` ends the stream; `0xFF lo hi` says the stream goes on at another address |
| `0x01..0x10` | skip n bytes |
| `0x20+n` | copy the n bytes that follow |
| `0x40+n` | fill n bytes with the byte that follows |
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
- Rows 48..96 are drawn once into both buffers. If anything else ever
  writes there — a horizon, a sun, a score — they have to be redrawn too.
- The stream's row entries are what the split at row 97 is cut on, so a
  repeat run may not straddle it. `tests/mkjetdata.py` cuts it there.
- 16 bytes wide starting at byte 56 of a row never crosses a page, which is
  why `skip` is one `ADD A,E`.

    python3 tests/jetpack.py /tmp/pilot.png   # look at him, 8x
    python3 tests/mkjetdata.py                # regenerate the stream
    python3 tests/test_chequer6.py            # verify against the model
