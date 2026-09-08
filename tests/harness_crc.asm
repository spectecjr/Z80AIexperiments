; Test scaffold for crc32.z80s. The bench pokes the data at DATA,
; sets HL/BC and calls whichever entry point it is testing.

DATA:           EQU 0xA000      ; where the bench puts the test buffer

                ORG 0x8000
                INCLUDE "crc32.z80s"
