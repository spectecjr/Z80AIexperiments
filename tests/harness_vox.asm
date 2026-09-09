; Test scaffold for vox.z80s.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "voxdata.z80s"
                INCLUDE "vox.z80s"
                ASSERT $ <= 0x2000
