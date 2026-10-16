# Authoritative TODO

- [ ] **BUILD-005 — Human-maintained AgonDev MOS foundation for EMOS**
  - Status: Native source/helpers committed locally; clean build and bounded
    headless boot/shell/two-cold-boot API qualification pass. Human shell checks
    passed; initial manual API review failed. Corrected root-based file and
    persistence checks pass unattended on both images; no manual API rerun is
    requested. The shared repeated-run failure is recorded as
    MOS-EXTRACTNUMBER-001. Physical qualification, qualified handoff and EMOS
    adoption remain gated. Author approved scoped commit/push on 2026-10-16.
  - Details: [BUILD-005](docs/tasks/BUILD-005.md)
  - Policy: [project policies](docs/POLICIES.md)
  - Priority: Extender/EMOS first; UART is deferred. Prior BUILD-003/004
    investigations are disposed in the dated log, with reusable-tool promotion
    carried into this task.

- [ ] **API-001 — Canonical API allocations and firmware/interface identity**
  - Status: Policy accepted 2026-10-16. Author subsequently authorized the
    bounded reservation slice: foundation main owns the register and generated
    assembly/C bindings; UART keeps experimental getfunction 0x13 in its own
    project. Namespace/collision/consistency checks are implemented locally.
    Complete firmware/banner identity, distribution and wider namespace
    coordination remain unfinished; no official SDK/reference was edited.
  - Policy: [canonical definitions](docs/POLICIES.md#canonical-api-definitions-and-reservations)
    and [build identity](docs/POLICIES.md#firmware-and-interface-build-identity).
  - Scope excludes qsort and does not reopen UART integration into foundation
    or EMOS. Separately authorized custom UART development stays with its owner.

- [ ] **TEST-002 — Opt-in UART1 transmit-interrupt model for resident service tests**
  - Status: Bounded machine checks complete: 138 generic tests and the consuming fixed native case pass. Default source output and all references stay unchanged. Author authorized candidate commit/publication on 2026-09-14; human emulator validation remains open.
  - Details: [TEST-002](docs/tasks/TEST-002.md)

Product-specific implementation and release gates belong to their maintained
source repositories. Completed generic PORT-200 qualification is summarized in
`docs/port-200-qualification.md`.
