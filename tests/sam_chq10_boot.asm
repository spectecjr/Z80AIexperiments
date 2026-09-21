; Six instructions in the bank's own spare bytes, which is the only
; code that can be running at the moment the loader hands over: the
; high block is about to stop being the loader's page and start being
; a buffer, so whatever does that has to be in the low block, and the
; low block is the bank.
        DEVICE NOSLOT64K
        ORG DEMO_BOOT
demo_boot:
        LD   SP,0x7FF0          ; the stack the bank leaves room for
        LD   A,DEMO_SCR0
        OUT  (251),A            ; a buffer pair, so the resident block
        JP   DEMO_GO            ; is at 0xE000 - and there it is
