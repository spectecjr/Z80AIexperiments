; chequer7, paged: the resident block - the board's code, the city's,
; the pilot's player and its three poses of stream, in the 8K a MODE 4
; screen leaves spare at the end of its odd page, with a copy behind
; each buffer. The board's bank is chequer5's, in pages of its own.
;
; The pilot's streams are the ones cut at the city's top row rather
; than the board's, because the city moves under him.
        DEVICE NOSLOT64K
CHQ4_PAGED:     EQU 1
CHQ4_DYNHZ:     EQU 0           ; the horizon stands still here
CHQ6_CITY:      EQU 1            ; the band between the board and the sky
chq4_band:      EQU 0x0000      ; the bank's bands, at the foot of it
        ORG 0xE000
        INCLUDE "chequer5equ.z80s"
        INCLUDE "citydata.z80s"
        INCLUDE "jetdata7.z80s"         ; before the player, which DUPs
        INCLUDE "chequer7.z80s"         ; over the pilot's width
        INCLUDE "chequer6.z80s"
        INCLUDE "chequer4.z80s"
        ASSERT $ <= 0x10000
