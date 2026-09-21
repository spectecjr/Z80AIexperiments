; A stopwatch for the host, not for the SAM.
;
; It counts DEMO_TICKS frame interrupts by polling the status port - the
; bit is low for 128 T-states of every 119,808, so each one is counted
; once - and then halts with interrupts off, which is SimCoupe's
; -exitonhalt signal to quit. Run it twice with different counts and the
; difference in wall time over the difference in frames says how fast the
; host was running the emulator, with the boot and the load cancelling
; out. Anything measured against the clock on a machine that cannot keep
; up with an emulated 6 MHz needs that number.
        DEVICE NOSLOT64K
        ORG 0x8000
tick_go:
        DI
        LD   BC,0x00F9          ; the status port, all keyboard rows
        LD   DE,DEMO_TICKS
tick_low:
        IN   A,(C)              ; wait for the interrupt to go active
        AND  0x08
        JR   NZ,tick_low
tick_high:
        IN   A,(C)              ; and for it to clear, so the next low
        AND  0x08               ; edge is the next frame and not this one
        JR   Z,tick_high
        DEC  DE
        LD   A,D
        OR   E
        JR   NZ,tick_low
        HALT                    ; with interrupts off: -exitonhalt quits
