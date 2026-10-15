# Authoritative TODO

- [ ] **BUILD-003 — Explain pinned EMOS ZDS II versus AgonDev ROM size**
  - Status: Registered on `main`; workspace setup and investigation await Author discussion.
  - Details: [BUILD-003](docs/tasks/BUILD-003.md)
  - Track this cross-toolchain investigation here by explicit Author direction;
    EMOS implementation ownership remains in `agon-emos`.

- [ ] **TEST-002 — Opt-in UART1 transmit-interrupt model for resident service tests**
  - Status: Bounded machine checks complete: 138 generic tests and the consuming fixed native case pass. Default source output and all references stay unchanged. Author authorized candidate commit/publication on 2026-09-14; human emulator validation remains open.
  - Details: [TEST-002](docs/tasks/TEST-002.md)

Product-specific implementation and release gates belong to their maintained
source repositories. Completed generic PORT-200 qualification is summarized in
`docs/port-200-qualification.md`.
