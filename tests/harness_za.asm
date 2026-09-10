                ORG 0x0000
                HALT
                DEFS 0x0100-$
                INCLUDE "zarchdata.z80s"
                INCLUDE "zarch.z80s"
                ASSERT $ <= 0x2000
