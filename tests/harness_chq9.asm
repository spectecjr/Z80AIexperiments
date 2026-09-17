; chequer9, paged: the resident block - the board's code with a horizon
; that moves, the desert's, and the frame that ties them together - in the
; 8K a MODE 4 screen leaves spare at the end of its odd page, with a copy
; behind each buffer. The board's bank is six chunks of compiled bodies
; covering squares up to 96 pixels wide; the desert's rear layer is three
; more.
        DEVICE NOSLOT64K
CHQ4_PAGED:     EQU 1
CHQ4_DYNHZ:     EQU 1           ; the horizon is a runtime choice
C9_DYNHZ:       EQU 1           ; and the desert's band follows it
CHQ6_CITY:      EQU 0
chq4_band:      EQU 0x0000      ; the bank's bands, at the foot of it
        ORG 0xE000
        INCLUDE "chequer9equ.z80s"
        INCLUDE "chequer9hz.z80s"
        INCLUDE "desert9data.z80s"
        INCLUDE "desert.z80s"
        INCLUDE "chequer9.z80s"
        INCLUDE "chequer4.z80s"
        ASSERT $ <= 0x10000
