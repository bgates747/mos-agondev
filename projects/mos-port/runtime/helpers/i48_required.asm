; Split out the only two 48-bit compiler stubs required by the MOS C objects.
;
; AgonDev's i48stubs.o places every 48-bit stub in one .text section. Pulling
; either one consequently retains the complete 64-bit helper closure. These
; two routines preserve the implementation and ABI of AgonDev 1.0 while
; allowing the firmware runtime to select only __llmulu and __llshru.

	.assume adl=1
	.section .text
	.global __i48shru
	.extern __llshru
__i48shru:
	push bc
	ld bc, 0
	call __llshru
	pop bc
	ret

	.section .text
	.global __i48mulu
	.extern __llmulu
__i48mulu:
	push hl
	or a, a
	sbc hl, hl
	ex (sp), hl
	push iy
	push bc
	call __llmulu
	pop bc
	pop iy
	inc sp
	inc sp
	inc sp
	ret
