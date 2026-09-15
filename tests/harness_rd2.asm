        ORG 0x0000
        HALT
        DEFS 0x0100-$
        INCLUDE "roaddata2.z80s"
        INCLUDE "road2.z80s"
        ASSERT $ <= 0x2000              ; the low block, under the screens
        DEFS 0xE000-$
        INCLUDE "roaddata2hi.z80s"
        ASSERT $ <= 0xFEC0              ; the high one, clear of the stack
