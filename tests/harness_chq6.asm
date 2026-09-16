; chequer6, paged: the resident block - the board's code, the pilot's
; player and its three poses of stream, in the 8K a MODE 4 screen leaves
; spare at the end of its odd page, with a copy behind each buffer. The
; board's bank is chequer5's, in pages of its own.
        DEVICE NOSLOT64K
CHQ4_PAGED:     EQU 1
chq4_band:      EQU 0x0000      ; the bank's bands, at the foot of it
        ORG 0xE000
        INCLUDE "chequer5equ.z80s"
        INCLUDE "jetdata.z80s"          ; before the player, which DUPs
        INCLUDE "chequer6.z80s"         ; over the pilot's width
        INCLUDE "chequer4.z80s"
        ASSERT $ <= 0x10000
