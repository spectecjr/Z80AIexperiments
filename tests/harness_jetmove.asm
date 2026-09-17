; The pilot's page, which LMPR maps at 0x0000 for the length of one call:
; three poses of compiled sprite, each one walk of the stack pointer from
; the byte after his bottom right corner to his top left, and the table
; that reaches them. CQ9_RET comes from the resident assembly: the way
; back is the one address the page has to know.
        DEVICE NOSLOT64K
CQ9_RET:        EQU CQ9_R
        INCLUDE "jetmove.z80s"
