; The tree's page, which LMPR maps at 0x0000 for the length of one call:
; the eight sizes of compiled sprite, each one walk of the stack pointer
; from the byte after the bottom right corner of its box to the top left,
; and the table that reaches them. CQ10_RET comes from the resident
; assembly: the way back is the one address the page has to know.
        DEVICE NOSLOT64K
CQ10_RET:       EQU CQ10_R
        INCLUDE "tree.z80s"
