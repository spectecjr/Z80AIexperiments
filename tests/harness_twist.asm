; Test scaffold for twist.z80s.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "twist.z80s"
                INCLUDE "twistdata.z80s"
                ASSERT $ <= 0x2000
