# prism.z80s — design notes

A lit extruded logo, cut into convex quads and drawn with `renderlit.z80s`'s
own rasteriser. **461,171 T-states a frame, 13.0 Hz**, verified byte-for-byte
against `tests/prism.py` over 256 frames.

> **Two shapes.** `PRISM_SHAPE=entropy` builds the logo traced from
> `entropylogo.png` - nine convex pieces, 550,669 T-states a frame - and
> everything below is unchanged by it. The default is the provisional
> shape described next, which is seven pieces and cheaper.
>
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
| `pr_draw` | 197,046 | 44% — faces and fill, seven pieces |
| `pr_proj` | 83,969 | 19% — 56 corners projected, and seven screen boxes |
| `pr_light` | 73,704 | 17% — two transposed products, then 18 normals |
| `pr_order` | 33,161 | 7% — 21 separating planes, then a topological sort |
| `pr_tables` | 27,649 | 6% |
| `rndl_erase` | 24,022 | 5% — one box for the whole logo |
| `demo_spin` | 6,628 | 1% |
| `pr_box`, `rndl_flip` | 273 | — |
| **`pr_frame`** | **min 357,539, mean 446,602, max 513,944** | 13.4 Hz |

`pr_draw` came down from 243,950: renderlit's rasteriser was gone over a
second time (`renderlit.md`), and `pr_one` now works out each visible
face's colour itself and calls `rndl_quad` straight away. Going through
`rndl_setface` and then `rndl_six` meant writing two bytes for all six
faces and then walking all six again, for the two or three that get drawn.

**Ordering the pieces properly cost 3.5% of the frame.** The centroid
sort was 18,835 T-states and wrong; the separating planes are 33,161 and
right (below). Projecting before ordering rather than during drawing moved
80,000 T-states out of `pr_draw` into `pr_proj` and cost nothing.

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

## The faces that are inside the solid

The seven pieces are a cut-up of one plate, so **wherever two of them meet,
both own a side face on the join and neither face is on the outside of
anything**. The triangle is three trapezoids meeting at three mitred
corners — two buried faces at every corner — and the sigma's arms meet each
other and sit against the bars. Ten of the 42 faces, and because each pair
has opposite normals exactly one of the two passes the cull every frame:
measured, **4.6 faces and 429 pixels of fill a frame, 12% of all the fill**,
for surfaces that can never be seen.

Worse, they are what a wrong painter order shows. Two pieces ordered the
wrong way round only *look* wrong if the near one has a face where they
join — which is precisely one of these. Culling them makes most ordering
mistakes invisible as well as cheaper.

Bit 7 of a face's normal byte in `pr_face` says so (there are 18 normals,
so the bit was free), and `pr_one` forces the visibility byte to zero when
it is set. It cost 42,914 T-states a frame — 8% — to stop drawing them.
`tests/prism.py`'s `buried()` works the mask out from the geometry rather
than a list: a face is inside the solid when another piece owns an edge on
the same line, running the other way, that contains it.

## Blocks, not faces

The logo is drawn as seven convex prisms, one after another, so the only
thing that can put a face behind another is the order the prisms go in.
That is a painter's algorithm over blocks, and it has two failure modes.

**The first was the sort key.** A piece was placed by the view z of its
quad's centre. A centroid says nothing about which of two pieces is in
front where they actually overlap: measured against the geometry, it drew
**344 pairs the wrong way round in 178 of the 256 frames** — and the
sigma's arms and the triangle's mitred corners are exactly the pieces it
got wrong, so an interior wall would sit on top of an exterior one for a
dozen frames at a time.

**The fix is exact for this shape.** The pieces are disjoint convex prisms
of the same z extent, so for every pair the separating axis theorem
promises that one of the eight side faces has the other piece wholly on
its outward side. That plane settles the pair with no error at all:
whichever piece is on the eye's side of it is the nearer one — and "is the
eye outside this plane" is `N·T + off < 0`, the same test that culls faces,
whose `N·T` `pr_light` has already worked out. So the 21 pairs cost two
16-bit loads and an add each, and `pr_pair` carries the two addresses so
there is no arithmetic at all.

**The second failure mode is the one blocks cannot escape.** Pairwise
answers only give an order if the relation is acyclic, and it is only
acyclic if pieces that do not overlap on screen are left unconstrained —
so the sort is a topological one over the pairs whose screen boxes touch.
Boxes are not shapes, and in **36 of 256 frames** they leave a cycle where
the shapes would not. Then the piece in front of the fewest others goes
first, which leaves one pair the wrong way round instead of a cascade:

| | pairs drawn the wrong way round |
|---|---|
| centroid depth | 344, in 178 of 256 frames |
| **separating planes** | **36, in 36 of 256 frames** |

Nothing short of splitting the pieces — or ordering faces rather than
blocks — removes the last 36, though with the buried faces gone (above)
what a wrong pair now shows is one exterior surface instead of another,
rather than the inside of the logo. Every one of them is a cycle among screen
boxes, so testing the projected octagons instead would too; that is eight
2D separating-axis tests a pair and 21 pairs, which is not worth 36 frames
of one pair each.

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

- A face marked buried must really be buried: `buried()` proves it from the
  edges, so a piece that overlaps another rather than abutting it would
  mark a face that is not.
- Every pair of pieces must have a separating side face, and
  `tests/prism.py`'s `pairs()` raises if one does not. A piece that is not
  convex, or two that interpenetrate, breaks that and the order with it.
- `pr_pair` holds *addresses* into `pr_face` and `pr_nsh`, so it must be
  regenerated whenever either table's shape changes.
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
