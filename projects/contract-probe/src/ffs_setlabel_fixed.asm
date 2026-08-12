/*
 * The pinned libmos ffs_setlabel wrapper correctly exchanges the first C
 * argument into HL, then overwrites HL from an uninitialized IX frame. Keep
 * this project-local correction available until the redundant IX load is
 * removed upstream.
 */

        .assume adl=1
        .include "agon/mos.inc"
        .section .text
        .global _ffs_setlabel

_ffs_setlabel:
        pop     de
        ex      (sp),hl
        push    de
        ld      a,ffs_setlabel
        rst.lil 08h
        ret
