; Test scaffold for float32.z80s - see harness.asm for the float16 one.
;
; Operand pairs go in at DRV_IN as eight bytes each (a then b, both
; little-endian); results come back at DRV_OUT, four bytes each.

DRV_IN:         EQU 0xA000
DRV_OUT:        EQU 0xC000

                ORG 0x8000
                INCLUDE "float32.z80s"

                DEFS 0x9000-$   ; pad so --raw gives one contiguous image
drv_count:      DEFW 0          ; number of pairs, poked by the bench
drv_in:         DEFW 0
drv_out:        DEFW 0

drv_run:
                LD   HL,DRV_IN
                LD   (drv_in),HL
                LD   HL,DRV_OUT
                LD   (drv_out),HL
drv_loop:
                LD   HL,(drv_in)
                LD   D,H
                LD   E,L
                INC  DE
                INC  DE
                INC  DE
                INC  DE         ; DE = pointer to b
                PUSH DE
                INC  DE
                INC  DE
                INC  DE
                INC  DE
                LD   (drv_in),DE
                POP  DE
drv_call:
                CALL 0x0000     ; target poked by the bench
                PUSH DE
                LD   DE,(drv_out)
                EX   DE,HL
                LD   (HL),E
                INC  HL
                LD   (HL),D
                INC  HL
                POP  DE
                LD   (HL),E
                INC  HL
                LD   (HL),D
                INC  HL
                LD   (drv_out),HL
                LD   HL,(drv_count)
                DEC  HL
                LD   (drv_count),HL
                LD   A,H
                OR   L
                JR   NZ,drv_loop
                HALT
