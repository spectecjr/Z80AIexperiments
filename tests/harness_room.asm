; Test scaffold for room3d.z80s.
;
; The SAM layout: code and tables in the low 8K, the two 0x6000-byte
; screen buffers at 0x2000 and 0x8000. The code starts at 0x0100 only
; because the test bench uses 0x0000 as its return trap.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "mul8x8_qs.z80s"
                INCLUDE "room3d.z80s"
