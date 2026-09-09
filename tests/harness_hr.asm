; Test scaffold for harrier.z80s.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "harrierdata.z80s"
                INCLUDE "harrier.z80s"
                DEFS 0xF7C0-$
                INCLUDE "mul8x8_qs.z80s"
