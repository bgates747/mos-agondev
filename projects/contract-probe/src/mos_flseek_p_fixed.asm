/*
 * C places the uint8_t handle at SP+3 and the following uint32_t at SP+6.
 * AgonDev's pinned wrapper points MOS at SP+9 (the upper half of the six-byte
 * uint32_t slot). Keep this correction project-local until upstream uses SP+6.
 */

        .assume adl=1
        .include "agon/mos.inc"
        .section .text
        .global _mos_flseek_p

_mos_flseek_p:
        pop     de
        ex      (sp),hl
        push    de
        ld      c,l
        ld      hl,6
        add     hl,sp
        ld      a,mos_flseek_p
        rst.lil 08h
        ret
