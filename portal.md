# portal.z80s — design notes

A maze of nine convex rooms, drawn with `room3d.z80s`'s renderer by
recursing through the doors. **400,481 T-states a frame — 15 Hz mean, 11.5
Hz worst**, against room3d's 21.4 Hz for one room.

Verified byte-for-byte against `tests/portal.py` over 256 frames of a lap
of the ring corridor.

## The idea

room3d gets its whole design from the room being convex: the walls tile the
view exactly, so there is no sorting, no depth buffer and no overdraw, and a
wall is a screen-space trapezoid rather than a column of rays. A maze is not
convex. **A maze cut into convex sectors is, one sector at a time.**

So this is room3d's renderer driven recursively:

    draw(sector, window):
        for each wall:
            clip and project it, clamped to the window
            solid  -> file the strip
            a door -> draw(the sector behind it, the columns it lands between)

The windows do not overlap — the walls of a convex sector tile the view, so
the doors partition it — which means every pixel is still written exactly
once and the strips can still be filled straight down the stack.

A door seen from the far side is wound backwards, and room3d already throws
a backwards wall out, so **the recursion never walks back through the door
it came in by**. Depth is capped anyway (`P_DEPTH`, six), because a ring of
rooms can see itself.

The strips come out in recursion order rather than left to right, which
costs nothing: `r3d_rank` already sorts them by where they end.

## What room3d had to grow

Two things, both in what is now `r3d_wspan`:

- **A wall is clamped to `(r3d_wl)..(r3d_wr)`** instead of to 0..256.
  `r3d_frame` sets them to the whole screen, so one room renders exactly as
  it did; this file narrows them to a door.
- **The wall pipeline is split in two.** `r3d_wspan` clips, projects,
  clamps and snaps, returning carry set with the span; `r3d_wdraw` shades it
  and files the strip. A door wants the first without the second.

That refactor cost room3d 622 T-states a frame — 237,161 to 237,783 — and
its test still passes byte for byte.

Two harness knobs came with it: `R3D_WALLS` raises the strip and vertex
capacity (16 here, 8 by default), and `R3D_TAB` puts the rasteriser's table
somewhere else — at 0xE000 here, because sixteen strips' worth of it is
3,456 bytes and the low 8K is full.

## Where the camera may stand

**This is the one real limitation, and it is room3d's near plane.** A wall
whose ends are both nearer than `R3D_NEAR` in *depth* is thrown away, which
is right for a wall and wrong for a door: standing in a doorway, the door is
at depth zero and covers everything, but its projection is degenerate and
the sector behind it never gets drawn. The screen fills with ceiling and
floor where the walls should be.

Measured, in `tests/portal.py`: a hole appears exactly when the camera is
within about `NEAR + 10` of a door plane. So:

- **`p_here` is the caller's job**, and it must hand over to the next sector
  *before* the camera reaches the door — 48 units early here. A door that
  close covers more than the whole viewport, so the cell in front tiles the
  view on its own. The cell behind does not: what is behind the camera is
  exactly the part of it the door no longer shows.
- **Look ahead while going through a door.** `tests/portal.py`'s walk fades
  its looking-around out as it nears one. With that, 0 of 256 frames have a
  hole; with a fixed ±64° sweep, 4 do.

A renderer that wanted to lift this would have to clip a wall to the view
*cone* rather than to the near plane, and let the projection saturate.

## What it costs

| | T-states | |
|---|---|---|
| `r3d_raster` | 230,403 | 57% — room3d's floor, 18,432 bytes at 5.5 plus the row walk |
| the recursion and its walls | 124,120 | 31% — 14 walls looked at, 4.1 drawn |
| `p_xform` | 48,049 | 12% — all 16 vertices, every frame |
| **`p_frame`** | **min 285,275, mean 400,481, max 520,065** | |

Held to the flyback that rounds to whole 50ths, `demo/portal.gif` runs at
12.9 Hz: 56 frames at 60 ms, 99 at 80, 17 at 100, 8 at 120.

## If you pick this up

1. **`p_xform` transforms the whole maze every frame** — 48,000 T-states for
   16 vertices when the mean frame visits 3.4 sectors and needs about 8 of
   them. A "done this frame" bit per vertex would take most of that back,
   and it is the cheapest 6% here.
2. **A door could be rejected before it is projected.** The frustum reject
   in `r3d_wspan` is against the whole view; against the *window* it would
   throw out most of the 14 walls a frame looks at for a tenth of the price.
3. **The raster is 57% and is not going to move** — read room3d.md's own
   note on that. The maze does not make a pixel more expensive; it makes
   more walls arrive at the same raster.

## Invariants

- Every sector must be convex, wound clockwise in (x, z) as room3d's room
  is, and doors must be wound the same way from both sides.
- The camera must be inside `p_here`, or within a door's width of it — see
  above. Nothing checks.
- `R3D_WALLS` must be at least as large as the deepest strip count a view
  can produce; six here, sixteen allowed.
- `P_STACK` bounds the sectors waiting to be drawn; a full stack silently
  drops a door, which shows as a hole.

    python3 tests/mkportaldata.py   # regenerate the maze
    python3 tests/portal.py         # check the model tiles the view
    python3 tests/test_portal.py    # verify the Z80 against it and time
