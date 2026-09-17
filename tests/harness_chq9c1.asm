; Chunk 0 of chequer9's bank, which LMPR pages in at 0x0000: the band
; table at its foot, then the value sets, the tables of compiled bodies,
; the bodies themselves and the runs - for a stretch of bands, and
; needing nothing from any other chunk. CHQ4_RET comes from the resident
; assembly: a run's way back is the one address the bank has to know.
        DEVICE NOSLOT64K
chq4_ret:       EQU CHQ4_RET
chq3_ret:       EQU CHQ4_RET
chq5_ret:       EQU CHQ4_RET
        INCLUDE "chequer9c1.z80s"
