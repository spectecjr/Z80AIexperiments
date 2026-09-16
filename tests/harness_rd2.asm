; The resident block: this code and its tables live in the 8K a MODE 4
; screen leaves spare at the end of its odd page, with a copy behind
; each buffer. tests/sam.py loads it there, and the two bank chunks
; into pages of their own.
        DEVICE NOSLOT64K
        ORG 0xE000
        INCLUDE "roaddata2equ.z80s"
        INCLUDE "road2.z80s"
        INCLUDE "roaddata2rec.z80s"
        ASSERT $ <= 0x10000
