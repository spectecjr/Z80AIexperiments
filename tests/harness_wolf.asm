; Test scaffold for wolf3d.z80s.
;
; The SAM layout: code, tables and textures in the low 8K, the two
; 0x6000-byte screen buffers at 0x2000 and 0x8000, and above them the
; generated scaler bank (0xE000, up to 6,080 bytes), the quarter-square
; multiply and its table (0xF7C0), and one of the two per-frame product
; tables (0xFC00) - the other lives in the low 8K - which leaves the
; stack the last page. That is everything that is not screen in a plain
; 64K map. Both ends are checked: an ASSERT here for the low 8K, and
; the test for the scaler bank, which grows with the viewport and would
; otherwise walk into the multiply's table.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "wolfview.z80s"
                INCLUDE "wolf3d.z80s"
                INCLUDE "wolfdata.z80s"

                ASSERT $ <= 0x2000      ; the low 8K holds it all
                DEFS 0xF7C0-$           ; so its table aligns at 0xF800
                INCLUDE "mul8x8_qs.z80s"
