# Authoritative TODO

- [ ] **BUILD-005 — Human-maintained AgonDev MOS foundation for EMOS**
  - Status: First authorized tranche implemented locally for review. Private
    `agon-mos-agondev` retains official ancestry and readable native source;
    direct builds reproduce the stock control exactly. Runtime qualification,
    immutable handoff and EMOS adoption remain gated.
  - Details: [BUILD-005](docs/tasks/BUILD-005.md)
  - Policy: [project policies](docs/POLICIES.md)
  - Priority: Extender/EMOS first; UART is deferred. Prior BUILD-003/004
    investigations are disposed in the dated log, with reusable-tool promotion
    carried into this task.

- [ ] **API-001 — Canonical API allocations and firmware/interface identity**
  - Status: Policy accepted 2026-10-16; implementation not started or released
    by the documentation change. Coordinate interface ownership/reservations,
    shared versioned consumption, banner/header metadata and consistency checks
    before modifying firmware, SDKs or consuming projects.
  - Policy: [canonical definitions](docs/POLICIES.md#canonical-api-definitions-and-reservations)
    and [build identity](docs/POLICIES.md#firmware-and-interface-build-identity).
  - Scope excludes the qsort experiment and does not reopen EMOS/UART integration.

- [ ] **TEST-002 — Opt-in UART1 transmit-interrupt model for resident service tests**
  - Status: Bounded machine checks complete: 138 generic tests and the consuming fixed native case pass. Default source output and all references stay unchanged. Author authorized candidate commit/publication on 2026-09-14; human emulator validation remains open.
  - Details: [TEST-002](docs/tasks/TEST-002.md)

Product-specific implementation and release gates belong to their maintained
source repositories. Completed generic PORT-200 qualification is summarized in
`docs/port-200-qualification.md`.
