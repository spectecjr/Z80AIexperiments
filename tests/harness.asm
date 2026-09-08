; Test scaffold for float16.z80s.
;
; The Python bench (tests/bench.py) drives this under a Z80 emulator.
; Two ways in: call a routine directly, or fill the input buffer and
; run drv_run to work through a whole batch of operand pairs in one
; go, which is a great deal faster than crossing the emulator boundary
; for every single operation.

DRV_IN:         EQU 0xA000      ; operand pairs:  a.lo a.hi b.lo b.hi
DRV_OUT:        EQU 0xC000      ; results:        r.lo r.hi

                ORG 0x8000
                INCLUDE "float16.z80s"

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
                LD   C,(HL)
                INC  HL
                LD   B,(HL)
                INC  HL
                LD   E,(HL)
                INC  HL
                LD   D,(HL)
                INC  HL
                LD   (drv_in),HL
                LD   H,B
                LD   L,C
drv_call:
                CALL 0x0000     ; target poked by the bench
                LD   DE,(drv_out)
                EX   DE,HL
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
