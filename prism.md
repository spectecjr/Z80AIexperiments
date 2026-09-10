# prism.z80s — design notes

A lit extruded logo, cut into convex quads and drawn with `renderlit.z80s`'s
own rasteriser. **453,848 T-states a frame, 13.2 Hz**, verified byte-for-byte
against `tests/prism.py` over 256 frames.

> **The shape is provisional.** It is a serif sigma of 45° angles and a
> triangle with a triangular hole, built from a description rather than from
> the artwork. Nothing in the renderer depends on it: `PIECES` in
> `tests/prism.py` is seven quads and two colours, and everything else —
> vertices, faces, normals, plane offsets, the coordinate values the
> multiply tables need — is generated from them.

## The one idea

**An extruded quad has exactly a cube's shape: eight vertices and six quad
faces.** So a logo cut into convex quads is a handful of cubes that are not
cubes, and renderlit's face table, rasteriser, per-face colour and
visibility bytes all work unchanged. Order the eight vertices as renderlit
indexes them — its bit 2 is the x sign, bit 1 the y sign, bit 0 the z sign,
so the quad's corners go in as (+,+), (+,−), (−,−), (−,+), each one twice —
and its six faces *are* the prism's: four sides on the four edges, then the
front and the back.

What has to be found rather than assumed is per face, and all of it is
object-space constant:

| | |
|---|---|
| **the normal** | a side's is its edge's 2D normal, the front and back's is the z axis |
| **the plane** | renderlit tests `N·T + S < 0` with `S` the cube's half size; here it is `N·T + (n·p)` for a point `p` on the face |
| **the order** | the pieces are convex and disjoint but the whole is not, so they are drawn back to front by the depth of their centres |

`N·L` and `N·T` are the same two transposed matrix-vector products renderlit
already computes, dotted with the face's own normal — and **a normal is
shared by every face that has it**, so that is done once per distinct normal
(18 of them) rather than once per face (42). A face is then one add and a
sign test.

Back-to-front by centre depth is exact whenever a plane separates two
pieces, which for a flat logo it does.

## The multiply tables

`transform3d` wants nine tables indexed by a vertex coordinate. `democube`
fills two entries of each, because a cube has only `+S` and `−S`; a full
build is 2,304 multiplies. A logo has more values but not many — nine x,
nine y and two z — so `pr_tables` fills exactly the entries the vertices
will read: **sixty multiplies a frame**, 27,569 T-states.

## Where the logo may sit, and how big

Two numbers pin it, and neither is taste:

- **`t3d` adds up to `r * 128` of rotated vertex onto the centre** and the
  sum must stay in a signed word, so `tz + r ≤ 255` units.
- **No vertex may come nearer than the reciprocal table's floor**, so
  `tz − r ≥ 40`.

That leaves `r ≤ 107`, which is the biggest this logo can be drawn: about a
twelfth of the screen face on and a sixth when a corner swings near. The
vertices are signed bytes, which caps a coordinate at 127 independently.

## What it costs

| | T-states | |
|---|---|---|
| `pr_draw` | 307,115 | 62% — seven pieces of transform, faces and fill |
| `pr_light` | 73,704 | 15% — two transposed products, then 18 normals |
| `pr_tables` | 27,569 | 6% |
| `pr_order` | 4,900 | 1% |
| `rndl_erase` | 24,233 | 5% — one box for the whole logo |
| `demo_spin` | 6,566 | 1% |
| **`pr_frame`** | **min 320,652, mean 453,848, max 543,135** | 13.2 Hz |

**Sorting cost 50,000 T-states before it was measured.** The bubble sort
asked `pr_zget` for a piece's depth on every comparison — 72 transforms
where seven would do. Depths into a table first, then sort the table: 11% of
the frame back.

## If you pick this up

1. **`pr_light` is 15% for 18 normals**, which is 2,000 T-states each and
   too much for two multiplies and some pointer walking. `pr_dot` reloads
   its pointers from memory every component; in registers it would be half.
2. **`pr_draw` is 62% and most of it is renderlit's span fill**, which is
   close to its floor — but a logo is mostly slivers seen edge on, and a
   face whose projected area is under a few dozen pixels costs more in edge
   walking than it pays back. Rejecting those would be worth measuring.
3. **Seven pieces is the shape's doing, not the renderer's.** Fewer, larger
   convex pieces would cost less everywhere.

## Invariants

- Quads must be convex and wound clockwise with y up; `_clockwise` in the
  model enforces it, and renderlit's face table assumes it.
- The eight vertices must go in renderlit's index order. Get that wrong and
  the sides are drawn as diagonals.
- Every coordinate value a vertex uses must be in the axis lists, or its
  multiply table entry is whatever was there last frame.
- `tz ± r` must respect both bounds above.

    python3 tests/mkprismdata.py   # regenerate the logo
    python3 tests/prism.py         # draw it flat, and say how big it gets
    python3 tests/test_prism.py    # verify the Z80 against it and time
