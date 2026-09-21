; chequer10's resident block, with the demo driver in the 8K a MODE 4
; screen leaves spare behind it. Everything here is harness_chq10.asm's
; - the same includes, in the same order, so the image the machine runs
; is the code the bench verified - and then the flight path and the
; driver that plays it.
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
        INCLUDE "jetmoveequ.z80s"
        INCLUDE "treeequ.z80s"
        INCLUDE "desert.z80s"
        INCLUDE "chequer10.z80s"
        INCLUDE "chequer4.z80s"
        INCLUDE "demo10data.z80s"
        INCLUDE "demo10.z80s"
        ASSERT $ <= 0x10000
