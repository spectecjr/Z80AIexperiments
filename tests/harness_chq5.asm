; chequer5, paged: the resident block - this code in the 8K a MODE 4
; screen leaves spare at the end of its odd page, with a copy behind
; each buffer. tests/sam.py loads it there and the bank and the mask
; tables into pages of their own.
        DEVICE NOSLOT64K
CHQ4_PAGED:     EQU 1
chq4_band:      EQU 0x0000      ; the bank's bands, at the foot of it
        ORG 0xE000
        INCLUDE "chequer5equ.z80s"
        INCLUDE "chequer4.z80s"
        ASSERT $ <= 0x10000
