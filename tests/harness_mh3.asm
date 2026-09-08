; Test scaffold for murmur3.z80s. The bench pokes the string at DATA,
; sets HL and BC, and calls murmur3_64 or one of the index routines.
;
; mult8x8_sjasm.z80s is a copy of 8x8multiply_r16.z80s with Zeus's "\"
; modulo operator rewritten for sjasmplus; bench.py generates it.

DATA:           EQU 0xA000      ; where the bench puts the test string
OUT:            EQU 0xB000      ; where the index routines write

                ORG 0x8000
                INCLUDE "murmur3.z80s"
                INCLUDE "mult8x8_sjasm.z80s"
