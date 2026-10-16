# Research archive

This directory preserves the narrative and evidence basis of the original
AgonDev feasibility study. It is historical context, not current setup
documentation and not an actionable task list.

- `research/feasibility-study.md` records the original question, experiments,
  risks, recommendation, and phased qualification rationale.
- `research/technical-precis-2026-08-12.md` is the pinned technical snapshot
  supporting that conclusion.
- `research/devlog/` preserves chronological decisions and acceptance evidence
  from the initial investigation and implementation.

Current onboarding lives in `README.md` and `STARTHERE.md`. Current technical
contracts are indexed by `docs/README.md`. The only unfinished-work list is
`TODO.md`. Machine-readable frozen measurements remain under `evidence/`.

## Later build investigations

1. [Pinned EMOS compiler-size analysis](build-003-2026-10-15.md) reproduces
   installed inputs and measures separate native compaction experiments.
2. [Stock MOS, EMOS and UART matrix](build-004-2026-10-15.md) separates
   source-feature costs from compiler/profile costs; EMOS-UART integration is
   still absent. Qualification boundaries and remaining work are in `TODO.md`.

## Exact baseline reproduction

`make baseline-check` compares configured inputs and generated probes with
`evidence/baseline.json`. It intentionally has stricter requirements than the
normal `make verify` development gate:

- the exact recorded source commits must be checked out;
- an `agon-docs` checkout at the recorded commit must be available at
  `agon-docs/`, or supplied with `AGON_DOCS_ROOT`;
- Fab must be supplied with `FAB_ROOT` when it is not at
  `fab-agon-emulator/`;
- exact hashes of the original Fab executable and Platform VDP module are
  checked even though valid local rebuilds may differ because compiler output
  embeds checkout and user paths; and
- the exact stock ZDS MOS/map pair must reproduce the historical oversized-VDP
  stale-length defect as the study's intentional negative control.

The current generic baseline uses the clean `agon-mos` oversized-packet
correction recorded in `evidence/baseline.json`, directly on public official
v3.0.2 commit `8336409351ee5314e02801a7b72a4f1bb5282519`. The older
`5f67b1ca...` study identity remains in dated research as historical provenance;
it is not the current reproducibility authority.
