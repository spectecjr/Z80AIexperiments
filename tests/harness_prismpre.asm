; Test scaffold for prismpre.z80s.
;
; No transform3d and no democube: the whole frame is a table, so the
; only thing prismpre needs from either is renderlit's default corner
; pointer, which is a label and nothing more. The records live in the
; low 8K with the code and the points go above the screen buffers.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "mul8x8_qs.z80s"
                INCLUDE "renderlit.z80s"
                INCLUDE "prismpre.z80s"
                INCLUDE "prismpredata.z80s"
; What is left of transform3d and democube: four labels renderlit's
; own light and transform paths mention, which prismpre never calls.
demo_screen:    DEFS 16
t3d_m:          DEFS 9
t3d_tx:         DEFS 2
t3d_ty:         DEFS 2
t3d_tz:         DEFS 2
                ASSERT $ <= 0x2000
                DEFS 0xE000-$
                INCLUDE "prismprepts.z80s"
                ASSERT $ <= 0xFE00
