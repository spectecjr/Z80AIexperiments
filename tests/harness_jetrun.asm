; The pilot's page, which LMPR maps at 0x0000 for the length of one call:
; three poses of compiled sprite and the table that reaches them. The back
; buffer's address comes from the resident assembly, because every store
; in here is an absolute one.
        DEVICE NOSLOT64K
CHQ4_SCREEN:    EQU CHQ4_SCR
        INCLUDE "jetrun.z80s"
