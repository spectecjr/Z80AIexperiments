                ORG 0x0000
                HALT
                DEFS 0x0100-$
                INCLUDE "saa.z80s"
                INCLUDE "strings.z80s"
                INCLUDE "stringsdata.z80s"
                ASSERT $ <= 0x2000
