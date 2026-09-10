;  The same routine with four blocks in a DI window instead of two: over
;  the 400 T-state brief, and here only so the test can measure what a
;  window costs, and so what the brief costs. See scroll8.md.
                ORG 0x0000
                HALT
                DEFS 0x0100-$
                DEFINE SC_BLOCKS_A_WINDOW 4
                DEFINE SC_WINDOWS_A_GROUP 4     ; so both builds run the
                                                ; group test the same
                                                ; number of times
                INCLUDE "scroll8.z80s"
                ASSERT $ <= 0x2000
