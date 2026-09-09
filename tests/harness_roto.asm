; Test scaffold for roto.z80s.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "roto.z80s"
                INCLUDE "rotodata.z80s"
                ASSERT $ <= 0x2000
