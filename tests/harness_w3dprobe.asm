; Cost of the candidate inner loops for a textured wall column.
; The viewport is half horizontal resolution, so one screen byte is one
; column of two pixels, and a column runs down the screen 128 bytes at
; a time.
                ORG 0x0000
                HALT
                DEFS 0x0100-$

; --- A: accumulator loop, texture stepped by a fixed point fraction ---
; HL = screen, BC = 128, DE = texture, IXL = rows, A' = frac
probe_acc:
        LD   BC,128
        LD   DE,texture
        LD   HL,0x8000
        LD   IXL,96
        XOR  A
        EX   AF,AF'
pa_loop:
        LD   A,(DE)         ; texel
        LD   (HL),A         ; screen
        ADD  HL,BC          ; next row
        EX   AF,AF'
        ADD  A,80           ; the step, 32 texels over 96 rows
        EX   AF,AF'
        JR   NC,pa_no
        INC  DE
pa_no:
        DEC  IXL
        JR   NZ,pa_loop
        RET

; --- B: unrolled, the texel advance baked in where it falls ---
; three rows to a texel, which is what a 96 row wall over 32 texels wants
probe_unr:
        LD   BC,128
        LD   DE,texture
        LD   HL,0x8000
        DUP  32
        LD   A,(DE)
        INC  DE
        LD   (HL),A
        ADD  HL,BC
        LD   (HL),A
        ADD  HL,BC
        LD   (HL),A
        ADD  HL,BC
        EDUP
        RET

; --- C: the same, but two columns at once where they share a texel ---
probe_unr2:
        LD   BC,127
        LD   DE,texture
        LD   HL,0x8000
        DUP  32
        LD   A,(DE)
        INC  DE
        LD   (HL),A
        INC  L
        LD   (HL),A
        ADD  HL,BC
        LD   (HL),A
        INC  L
        LD   (HL),A
        ADD  HL,BC
        LD   (HL),A
        INC  L
        LD   (HL),A
        ADD  HL,BC
        EDUP
        RET

; --- D: a flat run of the same byte, for comparison (no texture) ---
probe_flat:
        LD   BC,128
        LD   HL,0x8000
        LD   A,0x55
        DUP  96
        LD   (HL),A
        ADD  HL,BC
        EDUP
        RET

        ALIGN 256
texture:
        DEFS 256,0x3C
