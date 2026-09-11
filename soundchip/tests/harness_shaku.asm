                ORG 0x0000
                HALT
                DEFS 0x0100-$
                INCLUDE "saa.z80s"
                INCLUDE "shaku.z80s"
                INCLUDE "shakudata.z80s"
                ASSERT $ <= 0x2000
