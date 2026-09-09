# render.z80s — design notes

A MODE 4 renderer for the spinning cube that `democube.z80s` moves. Solid
faces, one colour each, double buffered, no clipping. `renderlit.z80s` is
this file with lighting added; read this one first, then that one's notes
for the differences.

Verified byte-for-byte against `tests/raster.py` over the 400 demo frames
of `tests/test_render.py`.

## Interface

| symbol | |
|---|---|
| `rnd_init` | blank both buffers, once |
| `rnd_frame` | erase what this buffer holds, draw, flip |
| `rnd_flip` | **stub** — where the hardware page swap goes |
| `rnd_colour` | six bytes, 0..15, faces in the order +X −X +Y −Y +Z −Z |
| `rnd_back`, `rnd_front` | the two buffer pages, 0x80 and 0x20 |

It reads the projected vertices `transform3d.z80s` leaves behind. The cube
is assumed to project wholly on screen — the box `democube.z80s` bounces it
inside guarantees that, and there is no clipping anywhere.

## The four decisions

**Cull in screen space, not world space.** Once everything is projected,
the sign of the face normal dotted with the view direction is the z of the
cross product of two projected edges:

    (x1-x0)*(y2-y0) - (y1-y0)*(x2-x0)

Two signed byte multiplies a face. No per-face normal, no 24-bit
arithmetic, and — the part that matters — it is exact with respect to what
is about to be drawn, so rounding can never let a back face paint over a
front one. (`renderlit.z80s` gives this up, because lighting needs the real
normals anyway; see its notes.)

**Two scanline arrays, not an edge list.** Each face's four edges are
walked with Bresenham: edges that descend write into one array, edges that
climb into the other. Every scanline of a convex quad gets exactly one
entry per side, so the fill reads them off in pairs. No sorting, no active
edge table, no divisions. An edge costs 39 T-states a scanline plus 27 for
each pixel it moves sideways.

**Erase by dirty rectangle, off the stack.** Each buffer remembers the
bounding box of what was drawn into it and only that is cleared next time —
a couple of thousand bytes rather than 24K — through `rnd_pushes`, so 5.5
T-states a byte instead of the ~30 an `LD (HL),0` loop costs. Mean erase is
12,642 T-states.

**Fill spans byte-wise with nibble masks at the ends.** The middle of a
span is whole bytes; the two ends may be half a byte.

## Invariants — the things that broke, and must not be re-broken

**Mask polarity.** The end-of-span combine is

    LD A,(HL) : XOR C : AND E : XOR C : LD (HL),A

which keeps the *old* pixels where the mask bit is set. So `E` is a
**keep**-mask and must be the complement of the pixels being written. Both
end masks are built as complements (`SBC A,A` then `AND 0xF0`, or `CPL`
then `AND 0x0F`). Writing the obvious mask instead paints the inverse of
the span, which is how this was found.

**Slivers.** Where the two sides of a face cross, a scanline comes out with
xl > xr. It must be **skipped**, not swapped — swapping draws a spurious
run across the face. The test is `LD A,D : CP E : JR C,ok` before the span
call.

**`rnd_pushes` is entered n from the end.** 64 `PUSH HL` at `ALIGN 128`
ending in `JP (IY)`. The alignment, the count and the entry arithmetic are
one mechanism; change any of them together.

**No page-aligned small tables.** `rnd_colour`, `rnd_qx`, `rnd_qy` are
indexed by `LD HL,base : ADD HL,DE` and reached within a face by
`SET 2,L` / `RES 2,L`. An earlier version assumed page alignment that the
assembler had stopped providing, and drew nothing at all.

## What it costs

Over the 400 demo frames, T-states:

|  | min | mean | max |
|---|---|---|---|
| `rnd_frame` | 43,807 | 86,717 | 116,941 |
| one face visible | 43,807 | 60,540 | 74,880 |
| two faces | 61,415 | 81,755 | 102,184 |
| three faces | 80,245 | 99,221 | 116,941 |
| `rnd_erase` alone | 119 | 12,642 | 17,717 |

Mean frame: span fill 46,488 (55%), edge walk 15,752 (19%), erase 12,774
(15%), cull 4,919 (6%), gather 2,192 (3%), dirty box 1,742 (2%).

1,536 bytes: 864 code, 66 of PUSHes, the rest tables and workspace.

## Tried and rejected

**Filling span middles off the stack pointer.** 88,668 T-states a frame
against 87,411 for the byte loop — a net loss, and reverted. At the span
lengths a cube produces, the SP save and restore and the two odd ends cost
more than the PUSHes save. The stack fill is worth it for the erase, where
the runs are long and both ends are free, and not here.

## If you pick this up

The span fill is 55% of the frame and is close to the floor for this shape;
there is no large win left in this file. The interesting direction was
lighting, which is `renderlit.z80s`.

    python3 tests/test_render.py        # needs sjasmplus, pip install z80 numpy
