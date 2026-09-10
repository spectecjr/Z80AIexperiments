; Test scaffold for prism.z80s.
;
; The transform's multiply tables go above the screen buffers, as
; renderlit's own harness puts them; everything else is in the low 8K.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "mul8x8_qs.z80s"
                INCLUDE "democube.z80s"
                INCLUDE "renderlit.z80s"
                INCLUDE "prism.z80s"
                INCLUDE "prismdata.z80s"
                ASSERT $ <= 0x2000
                DEFS 0xE000-$
                INCLUDE "transform3d.z80s"
