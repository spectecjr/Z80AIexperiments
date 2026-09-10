# prism.z80s — design notes

A lit extruded logo, cut into convex quads and drawn with `renderlit.z80s`'s
own rasteriser. **518,273 T-states a frame, 11.6 Hz**, verified byte-for-byte
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
| `pr_draw` | 367,029 | 71% — seven pieces of transform, faces and fill |
| `pr_light` | 73,704 | 14% — two transposed products, then 18 normals |
| `pr_tables` | 27,649 | 5% |
| `rndl_erase` | 24,022 | 5% — one box for the whole logo |
| `pr_order` | 18,835 | 4% |
| `demo_spin` | 6,628 | 1% |
| `pr_box`, `rndl_flip` | 273 | — |
| **`pr_frame`** | **min 381,665, mean 518,273, max 606,432** | 11.6 Hz |

**A sign cost 13% of the frame — in the other direction.** The side faces
were culled and drawn the wrong way round for a while (below), so most of
what the rasteriser was asked to fill it filled with nothing. Getting them
right put 64,000 T-states a frame back on the bill: 453,848 was the cost of
a logo missing three sides in four.

**Sorting cost 50,000 T-states before it was measured.** The bubble sort
asked `pr_zget` for a piece's depth on every comparison — 72 transforms
where seven would do. Depths into a table first, then sort the table: 11% of
the frame back.

## The sign that hid the sides

The first version drew the front face of every piece and almost nothing
else. From some angles a side would appear; from others there would be two
or three stray pixels along an edge where a whole face should have been.

The edge normal was inward. For a quad wound clockwise with y up the
outward normal of the edge `p0 → p1` is `(-dy, dx)`; `(dy, -dx)` is the
inward one, and it was `(dy, -dx)`. That inverts the visibility test, so a
side was kept exactly when it should have been culled — and **a face kept
wrongly is wound backwards on screen**. renderlit walks descending edges
into one scanline array and ascending edges into the other, so a backwards
face puts the right chain in the left array: every span comes out with its
left end past its right end and fills nothing. The face did not look wrong.
It was not there. The stray pixels were the two or three rows near the ends
where the crossed chains happen to be in order again.

Measured over 256 frames of the model, with the inward normal 3,872 of the
5,238 faces the test kept were wound backwards and 1,263 of them drew
nothing at all. With the outward normal, 106 of 4,580 — and **no
correctly-wound face fills short**: every one of those 106 is a face within
a few units of edge on, whose projection is a sliver a fraction of a pixel
wide that integer rounding tips one way or the other. The worst of them
paints 16 pixels.

`check_faces` in `tests/test_prism.py` is the invariant that would have
caught it in a second rather than a day: for all 42 faces, Newell's normal
of the four vertices **in the order renderlit's face table names them**
must point the same way as the declared normal, and all four vertices must
lie on the plane the visibility test uses. With the inward normal it
reports 28 of 42 wrong.

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
- **A face's normal must agree with the winding of the same face's four
  vertices**, or it is culled when it should be drawn and drawn — as
  nothing — when it should be culled. `check_faces` in the test checks
  every face against Newell's normal, and its plane against its vertices.
- The eight vertices must go in renderlit's index order. Get that wrong and
  the sides are drawn as diagonals.
- Every coordinate value a vertex uses must be in the axis lists, or its
  multiply table entry is whatever was there last frame.
- `tz ± r` must respect both bounds above.

    python3 tests/mkprismdata.py   # regenerate the logo
    python3 tests/prism.py         # draw it flat, and say how big it gets
    python3 tests/test_prism.py    # verify the Z80 against it and time
