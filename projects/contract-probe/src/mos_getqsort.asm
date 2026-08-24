	.assume	adl=1
	.include "agon/mos.inc"
	.section .text
	.global	_mos_getqsort
	.equ	mos_function_qsort,0x12

/* Return MOS C-function slot 0x12, or NULL when the running MOS predates it. */
_mos_getqsort:
	ld	c,0
	ld	b,mos_function_qsort
	ld	a,mos_getfunction
	rst.lil	08h
	ret
