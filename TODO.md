# Authoritative TODO

- [ ] **BUILD-005 — Human-maintained AgonDev MOS foundation for EMOS**
  - Status: Author direction accepted; guidance recorded and Extender ownership
    contract agreed. Author selected private `agon-mos-agondev` and released the
    first native-source/build/readability tranche; EMOS adoption remains gated.
  - Details: [BUILD-005](docs/tasks/BUILD-005.md)
  - Policy: [native foundation](docs/native-foundation-policy.md)
  - Priority: Extender/EMOS first; UART is deferred. Prior BUILD-003/004
    investigations are disposed in the dated log, with reusable-tool promotion
    carried into this task.

- [ ] **TEST-002 — Opt-in UART1 transmit-interrupt model for resident service tests**
  - Status: Bounded machine checks complete: 138 generic tests and the consuming fixed native case pass. Default source output and all references stay unchanged. Author authorized candidate commit/publication on 2026-09-14; human emulator validation remains open.
  - Details: [TEST-002](docs/tasks/TEST-002.md)

Product-specific implementation and release gates belong to their maintained
source repositories. Completed generic PORT-200 qualification is summarized in
`docs/port-200-qualification.md`.
