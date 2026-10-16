# Current technical documentation

This directory contains current contracts and durable maintenance references.
It does not contain fresh-clone instructions, the authoritative task list, or
the original feasibility narrative.

- [Project policies](POLICIES.md) is the consolidated policy authority for
  native source, canonical API definitions/reservations, firmware/interface
  identity and qualification. Ownership agreements and technical specifications
  remain linked authorities for their own scopes. The former
  `native-foundation-policy.md` is a compatibility redirect, not a second policy.
- `docs/assembly-compatibility-strategy.md` defines the maintained ZDS-oriented
  language, strict translation behavior, diagnostics, and generated-source
  boundary.
- `docs/uart-peer-emulator.md` describes controlled UART1 emulator tests and
  their limits.
- `docs/upstream-findings.md` records confirmed AgonDev and Fab defects, their local
  workarounds, and reproducible reports for upstream maintainers.
- `docs/port-200-qualification.md` records the completed generic portability,
  ABI, emulator, and public-input improvements retained from PORT-200.
- `projects/mos-port/README.md` describes the current firmware build.
- `projects/native-foundation/README.md` separates one-time migration, direct
  native building and exact control comparison. Its first-tranche implementation
  remains a review candidate; native source instructions belong to the private
  agon-mos-agondev repository.
- `projects/mos-port/asm/README.md` documents the implemented assembly frontend.
- `projects/mos-port/ld/README.md` documents the firmware linker contract.
- `projects/mos-port/runtime/README.md` documents the restricted runtime.
- `projects/mos-port/PARITY.md` defines the bounded behavioral comparison.
- `projects/binary-compare/README.md` defines the automated official-release
  binary/map/disassembly comparison and its fail-closed evidence labels.
- `projects/contract-probe/README.md` and
  `projects/contract-probe/WRAPPER_AUDIT.md` define the current target ABI
  evidence and its limits.

Use `STARTHERE.md` for setup and the normal development cycle. Use `TODO.md` for
unfinished work. Historical reasoning, dated measurements, and chronological
logs are under `research/`.
