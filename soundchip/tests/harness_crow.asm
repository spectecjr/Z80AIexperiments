                ORG 0x0000
                HALT
                DEFS 0x0100-$
                INCLUDE "crow.z80s"
                INCLUDE "crowdata.z80s"
                ASSERT $ <= 0x2000
