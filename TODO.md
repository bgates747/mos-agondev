# Authoritative TODO

- [ ] **BUILD-004 — Compare stock MOS, EMOS and UART additions across toolchains**
  - Status: Author-approved Stages 1–3 complete; paused for review before
    EMOS integration. Stock UART costs 2,573 ROM / 86 RAM bytes under each
    measured configuration; no translator extension was necessary.
  - Details: [BUILD-004](docs/tasks/BUILD-004.md)
  - Results: [2026-10-15 matrix](research/build-004-2026-10-15.md)
  - Investigation and comparison ownership stays here; maintained product
    source and behavior remain with their owning repositories.

- [ ] **BUILD-003 — Explain pinned EMOS ZDS II versus AgonDev ROM size**
  - Status: Initial tranche complete through B003-14; exact builds reproduced,
    size accounting closed, measured recommendations available. Promotion and
    acceptance await Author discussion.
  - Details: [BUILD-003](docs/tasks/BUILD-003.md)
  - Results: [2026-10-15 analysis](research/build-003-2026-10-15.md)
  - Track this cross-toolchain investigation here by explicit Author direction;
    EMOS implementation ownership remains in `agon-emos`.

- [ ] **TEST-002 — Opt-in UART1 transmit-interrupt model for resident service tests**
  - Status: Bounded machine checks complete: 138 generic tests and the consuming fixed native case pass. Default source output and all references stay unchanged. Author authorized candidate commit/publication on 2026-09-14; human emulator validation remains open.
  - Details: [TEST-002](docs/tasks/TEST-002.md)

Product-specific implementation and release gates belong to their maintained
source repositories. Completed generic PORT-200 qualification is summarized in
`docs/port-200-qualification.md`.
