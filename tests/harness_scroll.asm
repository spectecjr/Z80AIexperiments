                ORG 0x0000
                HALT
                DEFS 0x0100-$
                INCLUDE "scroll8.z80s"
                ASSERT $ <= 0x2000
