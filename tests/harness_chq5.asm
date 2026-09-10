                ORG 0x0000
                HALT
                DEFS 0x0100-$
                INCLUDE "chequer5data.z80s"
                INCLUDE "chequer4.z80s"
                INCLUDE "chequer5runlo.z80s"
                ASSERT $ <= 0x2000
                DEFS 0xE000-$
                INCLUDE "chequer5run.z80s"
