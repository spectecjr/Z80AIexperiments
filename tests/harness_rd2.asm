; Test scaffold for road2.z80s.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "roaddata2.z80s"
                INCLUDE "road2.z80s"
                DEFS 0xE000-$
                INCLUDE "roaddata2hi.z80s"
