; Test scaffold for portal.z80s.
;
; room3d's renderer, driven through doors, so its tables have to hold
; more strips than one room needs - and the rasteriser's table, which
; is the big one, goes above the screen buffers to make room.

                DEFINE R3D_WALLS 16
                DEFINE R3D_TAB 0xE000

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "mul8x8_qs.z80s"
                INCLUDE "room3d.z80s"
                INCLUDE "portal.z80s"
                INCLUDE "portaldata.z80s"
                ASSERT $ <= 0x2000
