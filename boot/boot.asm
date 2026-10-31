; boot.asm - a tiny x86 boot sector for ZERO (real-mode code, NASM syntax).
;
;   nasm -f bin boot/boot.asm -o boot.img
;   qemu-system-i386 -drive format=raw,file=boot.img
;
; The BIOS loads this 512-byte sector to 0x7C00 and jumps to it.
[BITS 16]
[ORG 0x7C00]

start:
    cli
    xor  ax, ax
    mov  ds, ax
    mov  es, ax
    mov  ss, ax
    mov  sp, 0x7C00
    sti

    mov  ax, 0x0003         ; 80x25 text mode (also clears the screen)
    int  0x10

    mov  si, banner
    call print

.loop:
    mov  ah, 0x00           ; wait for a key press
    int  0x16
    cmp  al, 13             ; Enter?
    je   .newline
    mov  ah, 0x0E           ; teletype output of the typed character
    mov  bx, 0x000A
    int  0x10
    jmp  .loop

.newline:
    mov  si, prompt
    call print
    jmp  .loop

; print: SI = address of a zero-terminated string
print:
    mov  ah, 0x0E
    mov  bx, 0x000B
.next:
    lodsb
    test al, al
    jz   .done
    int  0x10
    jmp  .next
.done:
    ret

banner db 'ZERO boot sector - this is real x86 code', 13, 10
       db 'The ZX-16 machine lives one layer above. Type something:', 13, 10
prompt db 13, 10, '> ', 0

times 510 - ($ - $$) db 0   ; pad to 510 bytes
dw 0xAA55                   ; boot signature
