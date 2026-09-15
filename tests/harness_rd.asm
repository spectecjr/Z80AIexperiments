; Test scaffold for road.z80s.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "roaddata.z80s"
                INCLUDE "road.z80s"
