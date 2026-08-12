# Authoritative TODO

This is the project's only actionable task list. IDs are stable; completed,
rejected, or superseded work is recorded in the current development log and
removed from this file.

## Qualification gate

- [ ] **PORT-001** — Human-qualify the generated stock Platform MOS/VDP profile:
  banner and prompt, keyboard input, local SD selection, clean exit, and clean
  upstream emulator trees; then explicitly decide whether this scaffold may be
  committed.

## First AgonDev-built image

- [ ] **PORT-101** — Implement and evaluate the strict ongoing ZDS-to-GAS
  compatibility frontend selected in `docs/assembly-compatibility-strategy.md`.
  Preserve scoped, anonymous, and macro-local label idioms without globalizing
  maintained-source labels; add lexical, diagnostic, golden, object, and
  disassembly tests before using it on all build-critical assembly.
- [ ] **PORT-102** — Complete and verify the production firmware linker/startup
  contract: reset, vectors, RAM jump table, initialized-data copy, BSS clear,
  chip-select constants, heap/stack symbols, and strict ROM/RAM assertions.
- [ ] **PORT-103** — Replace the experimental C compatibility layer with an
  audited hardware header and upstream-quality source changes, including the
  disk timestamp shift and `quickrand` implementation.
- [ ] **PORT-104** — Define an allow-listed firmware runtime. Provide compiler
  helpers and a formatter that supports MOS's 32-bit formats, binds output to
  raw MOS `putch`, and cannot pull application CRT or MOS-client wrappers.
- [ ] **PORT-105** — Produce a fully resolved `MOS.elf`, map, binary, and Intel
  HEX; add automated address/vector/size/symbol assertions and a Fab-compatible
  ROM descriptor table or map bridge for directory-backed SD access.

## Parity and release evidence

- [ ] **PORT-201** — Build emulator parity tests for boot, VDP handshake,
  keyboard, command execution, FatFS, RTC, UART, and the oversized VDP-packet
  regression, comparing with a same-source ZDS reference image where possible.
- [ ] **PORT-202** — Exercise exported MOS C/assembly ABI entry points and all
  used `printf`/`sprintf` format patterns with golden boundary cases.
- [ ] **PORT-203** — After emulator parity, define recovery procedures and run
  staged physical-hardware validation before treating the port as releasable.
