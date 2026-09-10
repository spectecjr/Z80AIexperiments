                ORG 0x0000
                HALT
                DEFS 0x0100-$
SPN_TOP:        EQU 64
SPN_ROWS:       EQU 128
                INCLUDE "spanfill.z80s"
spn_list:       DEFS 4096
                ASSERT $ <= 0x2000
