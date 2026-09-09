; Test scaffold for wolf3d.z80s in its 192x96 viewport.
;
; The SAM layout: code, tables and textures in the low 8K, the two
; 0x6000-byte screen buffers at 0x2000 and 0x8000, and above them the
; generated scaler bank (0xE000, 5,508 bytes), the quarter-square
; multiply and its table (0xF5C0), and the two per-frame product tables
; (0xFA00 and 0xFC00), which leaves the stack the last page. That is
; everything that is not screen in a plain 64K map, with about sixty
; bytes to spare; the test checks the scaler bank's size, so growing
; the height ladder will not silently run into the multiply's table.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "wolfview96.z80s"
                INCLUDE "wolf3d.z80s"
                INCLUDE "wolfdata.z80s"

                DEFS 0xF5C0-$           ; so its table aligns at 0xF600
                INCLUDE "mul8x8_qs.z80s"
