; chequer8, paged: the resident block - the board's code, the desert's, and
; the frame that draws everything from scratch - in the 8K a MODE 4 screen
; leaves spare at the end of its odd page, with a copy behind each buffer.
; The board's bank, the desert's rear layer and the pilot are all chunks
; of their own. C9_RET is what the desert's runs jump back to.
        DEVICE NOSLOT64K
CHQ4_PAGED:     EQU 1
CHQ6_CITY:      EQU 0           ; c8_frame calls the city itself
chq4_band:      EQU 0x0000      ; the bank's bands, at the foot of it
        ORG 0xE000
        INCLUDE "chequer5equ.z80s"
        INCLUDE "desertdata.z80s"
        INCLUDE "jetrunequ.z80s"
        INCLUDE "desert.z80s"
        INCLUDE "chequer8.z80s"
        INCLUDE "chequer4.z80s"
        ASSERT $ <= 0x10000
