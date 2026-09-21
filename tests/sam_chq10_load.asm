; The loader: one page of the image, and the only part of it that is
; not the demo.
;
; It exists because of two limits that pull in opposite directions. A
; linear load starts at page 1, so nothing can be loaded into page 0 -
; and the map the bench verified puts the bank's first chunk there,
; with the stack at 0x7FFE. And the file is read through a chain of
; sectors that stops at the end of side 0, which is 387,600 bytes -
; so the image cannot afford to pad over the four pages the buffers
; take, and the chunks have to ship back to back.
;
; Both come out in the wash if the loader moves the pages itself. It
; copies itself into page 26, which nothing else wants, and from there
; the whole low block is free to be mapped: a page at a time, in an
; order that never overwrites a chunk before it has moved, out through
; the staging half of its own pair and back into place.
        DEVICE NOSLOT64K
        ORG 0x8000

LOAD_LMPR:      EQU 250
LOAD_HMPR:      EQU 251
LOAD_ROMOFF:    EQU 0x20        ; LMPR: RAM over ROM 0
LOAD_HOME:      EQU 26          ; the pair the loader runs from, which is
                                ; past everything the map uses
LOAD_STAGE:     EQU 0xC000      ; and the half of it a page goes through
LOAD_TABLE:     EQU 0x9000      ; where the builder puts the moves
LOAD_RES:       EQU 0xA000      ; and the resident block

;------------------------------------------------------------------
; The entry point: the ROM lands here with page 1 at 0x8000
;------------------------------------------------------------------

load_entry:
        DI
        LD   A,LOAD_ROMOFF + 1  ; this page at 0x0000 as well, and carry
        OUT  (LOAD_LMPR),A      ; on there: the high block is about to
        JP   load_low - 0x8000  ; stop being this code
load_low:
        LD   A,LOAD_HOME
        OUT  (LOAD_HMPR),A      ; page 26 at 0x8000
        LD   HL,0x0000          ; the loader's whole page into it, which
        LD   DE,0x8000          ; is a copy of the code doing the copying
        LD   BC,0x4000
        LDIR
        JP   load_move          ; and on in the copy, where the low block
                                ; is free to be anything at all

;------------------------------------------------------------------
; The move: a page at a time, through the staging half of this pair
;------------------------------------------------------------------

load_move:
        LD   SP,0xBFF0          ; a stack in this page, which nothing
        LD   HL,LOAD_TABLE      ; moves and nothing stages through
load_m1:
        LD   A,(HL)             ; the page to move, or 0xFF for no more
        INC  A
        JR   Z,load_done
        DEC  A
        ADD  A,LOAD_ROMOFF
        OUT  (LOAD_LMPR),A      ; it, at 0x0000
        INC  HL
        PUSH HL
        LD   HL,0x0000
        LD   DE,LOAD_STAGE
        LD   BC,0x4000
        LDIR                    ; out to the staging half
        POP  HL
        LD   A,(HL)
        INC  HL
        ADD  A,LOAD_ROMOFF
        OUT  (LOAD_LMPR),A      ; where it belongs, at 0x0000
        PUSH HL
        LD   HL,LOAD_STAGE
        LD   DE,0x0000
        LD   BC,0x4000
        LDIR                    ; and back in
        POP  HL
        JR   load_m1

;------------------------------------------------------------------
; The resident block goes behind each buffer, and then the demo
;------------------------------------------------------------------

load_done:
        LD   A,LOAD_SCR0 + LOAD_ROMOFF
        OUT  (LOAD_LMPR),A      ; the buffer's odd page at 0x4000, so
        CALL load_res           ; its spare 8K is at 0x6000
        LD   A,LOAD_SCR1 + LOAD_ROMOFF
        OUT  (LOAD_LMPR),A
        CALL load_res
        LD   A,LOAD_ROMOFF      ; the bank, with the stack in it
        OUT  (LOAD_LMPR),A
        JP   LOAD_BOOT          ; and the stub that rides in its spare

load_res:
        LD   HL,LOAD_RES
        LD   DE,0x6000
        LD   BC,LOAD_RESLEN
        LDIR
        RET
