# Production firmware linker

`mos.ld` places reset at zero, Fab's optional 79-byte hostfs descriptor at
`0x6B`, interrupt vectors at `0x100`, startup at `0x220`, ROM text/rodata,
initialized DATA with a ROM load image and RAM VMA, BSS, the RAM interrupt jump
table, heap, and reserved stack. It defines the target/startup constants used
by maintained assembly and rejects layout overflow.

From the repository root, run
`.venv/bin/python -B projects/mos-port/ld/verify_linker.py`. The verifier checks
an isolated valid image and proves five malformed layouts are rejected.
