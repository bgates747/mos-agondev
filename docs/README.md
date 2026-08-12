# Current technical documentation

This directory contains current contracts and durable maintenance references.
It does not contain fresh-clone instructions, the authoritative task list, or
the original feasibility narrative.

- `docs/assembly-compatibility-strategy.md` defines the maintained ZDS-oriented
  language, strict translation behavior, diagnostics, and generated-source
  boundary.
- `docs/upstream-findings.md` records confirmed AgonDev and Fab defects, their local
  workarounds, and reproducible reports for upstream maintainers.
- `projects/mos-port/README.md` describes the current firmware build.
- `projects/mos-port/asm/README.md` documents the implemented assembly frontend.
- `projects/mos-port/ld/README.md` documents the firmware linker contract.
- `projects/mos-port/runtime/README.md` documents the restricted runtime.
- `projects/mos-port/PARITY.md` defines the bounded behavioral comparison.
- `projects/contract-probe/README.md` and
  `projects/contract-probe/WRAPPER_AUDIT.md` define the current target ABI
  evidence and its limits.

Use `STARTHERE.md` for setup and the normal development cycle. Use `TODO.md` for
unfinished work. Historical reasoning, dated measurements, and chronological
logs are under `research/`.
