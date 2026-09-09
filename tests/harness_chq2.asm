; Test scaffold for chequer2.z80s.
;
; The viewport tables are chequer's; the runs are 5K and go above the
; screen buffers, where chequer built its own.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "chequerdata.z80s"
                INCLUDE "chequer2tab.z80s"
                INCLUDE "chequer2.z80s"
                ASSERT $ <= 0x2000
                DEFS 0xE000-$
                INCLUDE "chequer2run.z80s"
