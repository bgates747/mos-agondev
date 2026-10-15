# BUILD-003 — Explain EMOS binary size under ZDS II and AgonDev

The installed EMOS image fits in flash with only 2,450 bytes free, while the
reported smallest ZDS II build exceeds capacity by 3,442 bytes. This task will
establish a reproducible comparison, explain the 5,892-byte difference, and
recommend measured remedies compatible with the Author's requirement to use
native ZDS II. Functionality must not be removed merely to fit before the
baseline discrepancy has been explained.

Status: registered 2026-10-15 on `mos-agondev` `main`. Setup and analysis have
not started. Pause for Author discussion before executing the phases below.
The authoritative open-work entry is in `TODO.md`; this document defines its
scope, inputs, sequence, and acceptance criteria.

Subtask IDs below are permanent; do not renumber or reuse them. Mark an item
`[x]` when complete or otherwise disposed, and record the outcome and evidence
beside it. Leave unfinished items `[ ]`.

## Ownership and workflow

The Author explicitly selected `mos-agondev` `main` for task tracking. Read
the current canonical `agon-dev-env/codex/AGENTS.md`, documentation and
environment guidance, and each affected repository's `AGENTS.md` and
`OWNERSHIP.md` before implementation. This task does not transfer EMOS product
ownership: EMOS source changes belong in `agon-emos`; reusable preparation,
build, and comparison tools belong in `mos-agondev`.

Use persistent investigation checkouts beneath `~/Agon/mystuff/worktrees/`.
Keep the canonical checkout on `main` for task administration. Experimental
source, generated builds, and intermediate reports remain in the investigation
workspace; promote reviewed maintained changes and selected durable evidence
to their owning repositories after a solution is settled. Record exact source
commits and hashes at milestones so the workspace can be reconstructed. Do not
overwrite existing directories or another agent's work. Temporary workspace
contents are not a substitute for durable evidence or normal backups.

## Pinned first target

| Input or measurement | Recorded value |
| --- | --- |
| Product | EMOS v0.1.24 |
| Build identity | `agon-emos-v0.1.24-b2026-10-07-23-11-33Z` |
| Maintained source commit | `cf10f0b1848346bc5d04056e4663bbbc166b2480` |
| Installed AgonDev payload extent | 128,622 bytes |
| Flash capacity | 131,072 bytes |
| Space remaining | 2,450 bytes |
| Reported ZDS speed-oriented ROM usage | 138,752 bytes |
| Reported ZDS size-oriented ROM usage | 134,514 bytes |
| Reported best-ZDS minus AgonDev difference | 5,892 bytes |
| AgonDev compiler | Clang 15.0.7, LLVM `c76386c0083e6a6236ff774275227e2389f85538` |
| Retained AgonDev C flags | `-Oz`; recover exact per-file commands and overrides |
| Reported ZDS toolchain | ZDS II eZ80Acclaim! 5.3.5 under Wine on Oryx |

Unpadded installed `MOS.bin` SHA-256:
`44d217b555f68a7d030bc0a89a2fa1d27f0fb537576f2925e90ef055b0a44d02`.

Full 128-KiB installed ROM readback SHA-256:
`6f83bc21558ea7dcb665b60c18aa3a5c3030367f901e3e32ccbbf99eaf7f4019`.

The Extender handoff reports a matching full-ROM verification on October 15.
These are investigation inputs to verify, not newly reproduced results. Do not
substitute current EMOS HEAD, a production selection, or a stock MOS release.
The ZDS links failed overlap/range checks and produced no installable candidate;
their reported usage must be checked against the AgonDev payload accounting.

## Phase 1 — Persistent isolated workspace and network orientation

1. [ ] **B003-01** — Create `~/Agon/mystuff/worktrees/` if absent and reserve a clearly named
   investigation directory, such as `emos-build-003/`, without replacing
   existing contents. Keep a workspace inventory and provenance record.
2. [ ] **B003-02** — Clone the `main` branch of `https://github.com/bgates747/mos-agondev.git`
   into that investigation directory as `mos-agondev/`. Record its exact commit
   and confirm whether published `main` matches the canonical local `main`;
   resolve any difference explicitly. Configure a root `.venv` and dependencies
   according to current project instructions. Recover the historical build
   machinery revision separately if reproducing the installed image requires it.
3. [ ] **B003-03** — Clone official upstream MOS from
   `https://github.com/AgonPlatform/agon-mos.git` into a different workspace
   directory, `agon-mos-zds/`, for isolated ZDS compilation and stock controls.
   Pin the appropriate upstream revision after inspecting EMOS lineage. Leave
   canonical reference checkouts unchanged.
4. [ ] **B003-04** — Create a separate `agon-emos-pinned/` clone from
   `https://github.com/bgates747/agon-emos.git` at the exact target commit above.
   This is the maintained-source input for the same-firmware comparison;
   upstream stock MOS alone cannot reproduce EMOS. Keep pristine inputs and
   separately recorded experimental compatibility edits.
5. [ ] **B003-05** — Read `agon-dev-env/codex/environment.md`, especially its ZDS and SSH
   sections, and the machine-local
   `agon-dev-env/.local/ssh-001/CONNECTIONS.md`. They own current discovery,
   hostnames, identities, sudo and shares. Use their current contract for Oryx
   build staging; do not copy connection recipes, old addresses or aliases here.
   Read the installed launcher and qualification limits before relying on C
   compiler execution. Stage remote builds only in project-owned isolated
   directories, with explicit input/output manifests.

## Phase 2 — Verify inputs and reproduce the baseline

6. [ ] **B003-06** — Locate and hash the retained records listed below. Recover exact source,
   profile, feature configuration, firmware identity, prepared-source changes,
   tool versions, runtime archives, and compiler/linker commands.
7. [ ] **B003-07** — Account for the exploratory ZDS edits: structure-copy initialization changed
   to explicit `memcpy`, and command-fallback declarations moved before
   executable statements. They are reported uncommitted and unqualified;
   preserve their original evidence and reproduce them as explicit patches in
   isolated copies. Establish feature and behavior equivalence before treating
   the size comparison as controlled.
8. [ ] **B003-08** — Reproduce the 128,622-byte AgonDev result from retained inputs, checking the
   binary hash and identity. Investigate any drift before comparing new output.
9. [ ] **B003-09** — Reproduce the reported 134,514-byte ZDS size result and retain the speed
   result as a secondary control. Capture failure diagnostics and maps even
   when the ROM does not fit. Never describe an overflowing link as installable.

## Phase 3 — Attribute the difference with scripts

10. [ ] **B003-10** — Establish comparable accounting: loaded code and initialized data, RAM VMA
   versus ROM LMA, reserved regions, linker gaps, alignment, terminal extent,
   HEX-to-binary conversion, and padding. Report each separately.
11. [ ] **B003-11** — Adapt the existing comparison machinery to inventory both maps and objects,
   pair modules and useful function anchors, and rank size contributions.
   Retain compiler-emitted assembly and disassembly where available. Normalize
   recognized relocation effects conservatively; preserve unexplained residuals.
12. [ ] **B003-12** — Measure potential contributors: C instruction selection, calling conventions,
   arithmetic helpers, formatter features, runtime/library selection, dead-code
   elimination, section retention, startup and linker placement. These are
   hypotheses until supported by counts, maps or bounded experiments.
13. [ ] **B003-13** — Review preparation and translation effects. Scoped/macro-local labels become
   GNU `.L` names; ordinary labels remain unchanged. Symbol spelling itself does
   not occupy ROM. Attribute emitted instruction/data or placement differences,
   rather than assuming label globalization explains the size gap.
14. [ ] **B003-14** — Present largest contributors first with side-by-side ZDS and AgonDev byte
   counts, exact evidence links, accounting totals, and a bounded unexplained
   remainder. Prefer repeatable scripts to manual whole-image inspection.

## Phase 4 — Recommendations and promotion

15. [ ] **B003-15** — Recommend the smallest justified changes for the required ZDS build. Give
   measured savings where available, identify estimates clearly, and explain
   behavior, ABI and maintenance risks. Preserve EMOS functionality unless the
   Author separately chooses a tradeoff after reviewing the explanation.
16. [ ] **B003-16** — Promote reviewed generic tooling and concise reproducible evidence into
   `mos-agondev` `main`; route EMOS source remedies into `agon-emos`. Preserve
   frozen evidence, exact commands, tool identities, source hashes and maps or
   an indexed artifact manifest. Keep proprietary tool bytes outside Git.
17. [ ] **B003-17** — Record results and the task disposition in the current dated development
   log, then update the authoritative TODO after acceptance. A bounded account
   of remaining unknowns is acceptable; unsupported attribution is not.

## Retained evidence to consult

Locations below are relative to `~/Agon/mystuff/`, except the explicitly marked
read-only reference. Resolve their current existence before use.

1. `agon-extender/agents/pingo-callback/build-final/`, including `provenance/`
   and `artifacts.json`.
2. `agon-extender/agents/pingo-callback/tools/selection.json`.
3. `agon-extender/agents/scroll001/firmware-check-r02/emos-verified.json`.
4. `agon-emos/docs/tasks/INTEG-015.md`.
5. `agon-mos/docs/uart0-extender-tranche.md`.
6. `agon-mos/experiments/uart0-extender/budget-results.json` and
   `summarize-budget.py`.
7. `agon-mos/build/uart0-extender/`.
8. `~/Agon/agon-mos/` is the distinct official read-only reference, not the
   Author's `mystuff/agon-mos` fork or the proposed ZDS workspace clone.

## Operating boundaries

This task authorizes offline build analysis after the discussion pause. It
does not authorize bench access, flashing, resets, SD deployment, hardware
tests, startup-file changes, or cross-partition access. AgonDev is the pinned
comparison baseline; native ZDS II remains the required EMOS toolchain.

The UART agent will supply proposed integration separately. First explain the
installed firmware's discrepancy; assess new UART integration only against
the established baseline in subsequent authorized work.
