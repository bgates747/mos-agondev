# Firmware-layout toolchain probe

This is a proof of toolchain capability, not MOS firmware. It demonstrates that
the installed AgonDev compiler, GNU assembler/linker, `libagon` compiler helpers,
and `objcopy` can produce an eZ80 ADL image with the essential MOS memory shape.

The linker script places reset at `0x000000`, a 288-byte vector region at
`0x000100`, startup/text at `0x000220`, initialized data at a flash LMA and RAM
VMA, and BSS in the eZ80F92 internal-RAM window. Link assertions enforce the
128 KiB flash and 16 KiB RAM limits.

From the repository root:

```bash
make toolchain-probe
```

The C source includes compile-time data-model assertions and a small ABI sample.
`make verify` prints the ELF header/sections, size, disassembly, and binary hash.
