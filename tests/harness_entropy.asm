; Test scaffold for prism.z80s drawing the traced Entropy logo.
;
; The same code as harness_prism.asm: prism.z80s is driven entirely by
; the numbers in its data file, so a nine-piece logo needs no changes.

                ORG 0x0000
                HALT                    ; the bench returns to here
                DEFS 0x0100-$
                INCLUDE "mul8x8_qs.z80s"
                INCLUDE "democube.z80s"
                INCLUDE "renderlit.z80s"
                INCLUDE "prism.z80s"
                INCLUDE "entropydata.z80s"
                ASSERT $ <= 0x2000
                DEFS 0xE000-$
                INCLUDE "transform3d.z80s"
