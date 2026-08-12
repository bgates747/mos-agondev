/*
 * AgonDev's pinned mos_getError wrapper reads the pointer immediately after
 * an eight-bit argument. Clang actually gives every C argument a three-byte
 * stack slot, as its call-site disassembly proves. Keep this project-local
 * correction until the upstream libmos wrapper uses +6/+9/+12 offsets.
 */

        .assume adl=1
        .include "agon/mos.inc"
        .section .text
        .global _mos_getError

_mos_getError:
        push    ix
        ld      ix,0
        add     ix,sp
        ld      e,(ix+6)
        ld      hl,(ix+9)
        ld      bc,(ix+12)
        ld      a,mos_getError
        rst.lil 08h
        pop     ix
        ret
