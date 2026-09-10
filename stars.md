# stars.z80s — design notes

A 3D starfield. **197,813 T-states a frame, 30.3 Hz, 192 stars**, verified
byte-for-byte against `tests/stars.py` over 256 frames.

## The one idea

**A star is a direction and a distance.** `x` and `y` are signed bytes, `z`
runs from 255 down to `ST_ZMIN`, and the screen offset from the middle is
`x * 64 / z`. That is `transform3d`'s projection with the rotation taken
out — one reciprocal lookup and two 8×8 multiplies — and it is the whole of
the arithmetic. `st_recip` is the same `256*64/z` table, which is also what
pins `ST_ZMIN` at 64: below that the reciprocal will not fit in a byte.

**Nothing is ever cleared.** A full screen erase is 135,000 T-states, which
is most of a 50 Hz frame on its own. Instead each star remembers the byte
it last lit *in each buffer* and blanks that nibble before lighting the new
one, so the cost is per star and not per screen. Two buffers is why there
are two sets of records: the byte to blank is the one from two frames ago.

Respawns come from a sixteen-bit LFSR with taps at 0, 2, 3 and 5, and **the
parity flag does the tap** — `AND 0x2D` leaves P/V set when an even number
of bits survived, so the feedback bit is the odd case, and the whole step is
an AND, a branch and two rotates.

## What it costs

| | T-states |
|---|---|
| **a star** | **1,030** |
| of which two `qsmul8` | 262 |
| and their sign handling | ~70 |
| the rest | ~700 of bookkeeping |
| **`st_frame`, 192 stars** | **min 188,852, mean 197,813, max 205,433** |

**The estimate in `demo-ideas.md` said 300 T-states a star and it was
wrong by three and a half times.** It counted the plot and the erase and
forgot that everything else — the reciprocal, two signed multiplies, the
byte address, the shade, walking two records — is four times that. At the
measured rate **116 stars fit a 50 Hz frame**; 192 fit 30 Hz.

## If you pick this up

1. **The bookkeeping, not the multiplies.** Two thirds of a star is index
   register accesses at 19 T-states each and re-reading fields that were
   already in hand. Interleaving the star with its two erase records so one
   pointer walks all of it, and caching `z` rather than reading it three
   times, is worth a few hundred.
2. **Whole-byte stars** — two pixels wide, no nibble masking — save about
   65 a star and a byte a record. Worth it if the count matters more than
   the look.
3. **The multiplies are not reducible.** `x * 64/z` needs a real 8×8, and
   `qsmul8` at 131 T-states is the cheapest exact one here.

## Invariants

- `ST_ZMIN` may not go below 64: `256*64/z` stops fitting a byte.
- `x` is a signed byte, so `128 + ox` cannot leave the screen and needs no
  clipping. `y` can, so it is range-checked and the star respawns — at the
  far plane, where it is always on screen, so one retry always succeeds.
- `ST_SEED` is the LFSR **after** the field was laid out, not the seed it
  started from, so the Z80's respawns line up with the model's.

    python3 tests/mkstarsdata.py     # the field and the tables
    python3 tests/test_stars.py      # verify against the model, and time
