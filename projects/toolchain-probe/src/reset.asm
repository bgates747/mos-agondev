        .assume ADL = 1

        .section .reset,"ax",@progbits
        .global _reset
        .extern _probe_main
        .extern __stack

_reset:
        di
        ld      sp, __stack
        jp      _probe_main

        .section .vectors,"ax",@progbits
        .global _probe_vectors
_probe_vectors:
        jp      _default_handler
        .space  0x11c, 0

        .section .startup,"ax",@progbits
_default_handler:
        ei
        reti.l
