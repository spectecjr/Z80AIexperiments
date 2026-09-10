; Test scaffold for cubes.z80s.
;
; democube for the spin, the step and the multiply tables; transform3d
; for the projection; renderlit for the light and the faces; cubes for
; four of them at once, with gravity and a room.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                DEFINE DEMO_HALF 34

                INCLUDE "mul8x8_qs.z80s"
                INCLUDE "democube.z80s"
                INCLUDE "renderlit.z80s"
                INCLUDE "cubes.z80s"
                INCLUDE "cubesdata.z80s"
                ASSERT $ <= 0x2000
                DEFS 0xE000-$
                INCLUDE "transform3d.z80s"
