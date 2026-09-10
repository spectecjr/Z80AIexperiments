; Test scaffold for balls.z80s.
;
; democube is here for its spin and its signed multiply; the labels its
; own frame path names are stubbed, since that path is never called.

                ORG 0x0000
                HALT
                DEFS 0x0100-$
                INCLUDE "mul8x8_qs.z80s"
                INCLUDE "democube.z80s"
                INCLUDE "balls.z80s"
                INCLUDE "ballsdata.z80s"
t3d_tx:         DEFS 2
t3d_ty:         DEFS 2
t3d_tz:         DEFS 2
t3d_run:        RET
t3d_tab:        EQU 0xE000
t3d_m:          DEFS 9
                ASSERT $ <= 0x2000
