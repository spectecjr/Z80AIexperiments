; Test scaffold for stars.z80s.

                ORG 0x0000
                HALT
                DEFS 0x0100-$
                INCLUDE "mul8x8_qs.z80s"
                INCLUDE "stars.z80s"
                INCLUDE "starsdata.z80s"
                ASSERT $ <= 0x2000
