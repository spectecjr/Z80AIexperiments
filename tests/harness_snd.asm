; The 50 Hz tick, on its own: the resident half in the high block, where
; the demos' resident code lives, and one chunk of log in the low one.
        DEVICE NOSLOT64K
SND_LMPR:       EQU 250
SND_BANK:       EQU 0x20        ; RAM over ROM 0, page 0: the log's chunk
SND_BENCH:      EQU 1           ; the two instructions that make the point
                                ; callable, which inline it does not have
        ORG 0xE000
        INCLUDE "snd.z80s"
        ASSERT $ <= 0x10000
