        .assume ADL = 1

        .section .reset,"ax",@progbits
        .global _reset
_reset:
        .byte   0xf3                    /* DI */
        .space  0x6a, 0

        .section .mos_descriptor,"a",@progbits
        .ascii  "MOS"
        .byte   2
        .space  0x4b, 0

        .section .ivecs,"ax",@progbits
        .global __vector_table
        .global __1st_jump_table
__vector_table:
        .space  0x60, 0                /* 48 two-byte IM 2 vectors */
__1st_jump_table:
        .space  0xc0, 0                /* 48 four-byte JP entries */

        .section .startup,"ax",@progbits
        .global __init
        .global __c_startup
__init:
        .byte   0x00
__c_startup:
        .byte   0x00

        .section .text,"ax",@progbits
        .global fixture_code
fixture_code:
        .byte   0xc9                    /* RET */

        .section .rodata,"a",@progbits
fixture_rodata:
        .byte   0x52, 0x4f, 0x4d

        .section .data,"aw",@progbits
        .global fixture_data
fixture_data:
        .byte   0xa5, 0x5a, 0x11, 0x22, 0x33

        .section .bss,"aw",@nobits
        .global fixture_bss
fixture_bss:
        .space  7

        .section .ivjmptbl,"aw",@nobits
        .global __2nd_jump_table
__2nd_jump_table:
        .space  0xc0
