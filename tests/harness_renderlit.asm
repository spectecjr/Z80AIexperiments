; Test scaffold for renderlit.z80s.
;
; The SAM layout this is written for: code and small tables in the low
; 8K, the two 0x6000-byte screen buffers at 0x2000 and 0x8000, and the
; transform's 4.6K of multiply tables above them at 0xE000. The code
; starts at 0x0100 rather than 0x0000 only because the test bench uses
; 0x0000 as its return trap.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "mul8x8_qs.z80s"
                INCLUDE "democube.z80s"
                INCLUDE "renderlit.z80s"
                DEFS 0xE000-$
                INCLUDE "transform3d.z80s"
