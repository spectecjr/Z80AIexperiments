; chequer5's run bank, which LMPR pages in at 0x0000: the bands, the
; records and the value sets at the foot of it, then the entry tables
; and the runs. CHQ4_RET comes from the resident assembly - a run's way
; back is the one address the bank needs to know.
        DEVICE NOSLOT64K
chq4_ret:       EQU CHQ4_RET
chq3_ret:       EQU CHQ4_RET
chq5_ret:       EQU CHQ4_RET
        ORG 0x0000
        INCLUDE "chequer5equ.z80s"
        INCLUDE "chequer5data.z80s"
        INCLUDE "chequer5runlo.z80s"
        INCLUDE "chequer5run.z80s"
        ASSERT $ <= 0x7F00              ; the caller's stack lives above
