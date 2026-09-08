; Test scaffold for 8x8multiply_r16.z80s (via the sjasmplus shim that
; bench.py generates from it).

IN:             EQU 0xA000      ; operand pairs for the streaming version
OUT:            EQU 0xB000      ; results

                ORG 0x8000
                INCLUDE "mult8x8_sjasm.z80s"
