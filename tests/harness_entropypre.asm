; Test scaffold for prismpre.z80s drawing the traced Entropy logo.
;
; Nine pieces is 184 bytes of table a frame against seven's 144, so the
; quarter-square multiply goes: prismpre does not multiply anything at
; all, and renderlit only names qsmul8 from paths it never calls. That
; is 1,280 bytes back, which is what makes 64 frames fit.

                ORG 0x0000
                HALT
                DEFS 0x0100-$
                INCLUDE "renderlit.z80s"
                INCLUDE "prismpre.z80s"
                INCLUDE "entropypredata.z80s"

; What is left of the modules prismpre does not use: labels renderlit's
; own light and transform paths mention, and a multiply it never calls.
demo_screen:    DEFS 16
t3d_m:          DEFS 9
t3d_tx:         DEFS 2
t3d_ty:         DEFS 2
t3d_tz:         DEFS 2
qsmul8:         RET
                ASSERT $ <= 0x2000
                DEFS 0xE000-$
                INCLUDE "entropyprepts.z80s"
                ASSERT $ <= 0xFE00
