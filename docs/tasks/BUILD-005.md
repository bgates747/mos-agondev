# BUILD-005 — Human maintained AgonDev MOS foundation for EMOS

Establish a readable, traceable native AgonDev MOS foundation for EMOS, without
making Extender development depend on experimental UART integration. Preserve
official ancestry and explain every meaningful local modification. The Author
accepted this direction on 2026-10-15 and subsequently approved the repository
identity, private GitHub creation and first foundation implementation tranche.
EMOS adoption and deployment remain outside this tranche.

Status: guidance recorded and contract v1 mutually accepted on 2026-10-15.
Repository: `bgates747/agon-mos-agondev`, private; local `../agon-mos-agondev/`,
relative to this repository root. First implementation tranche is authorized.
The authoritative work entry is in `TODO.md`; IDs below are permanent.
Accepted policy: [native foundation guidance](../native-foundation-policy.md).
Cross-owner agreement: [central contract](../../../agon-dev-env/cross-agent/mos_agondev_foundation/CONTRACT.md).
Measurements: [BUILD-003](../../research/build-003-2026-10-15.md) and
[BUILD-004](../../research/build-004-2026-10-15.md).

## Decisions and boundaries

AgonDev becomes authoritative for future foundation/EMOS development. The
existing translation build remains executable during transition. The foundation
is a separate firmware repository; mos-agondev remains reusable infrastructure.
EMOS product implementation and task tracking stay with their owner.

The first control uses official MOS v3.0.2 commit
`8336409351ee5314e02801a7b72a4f1bb5282519`. Do not import UART, overwrite
official references, rename another owner's checkout or adopt a post-release
fix implicitly. The Author selected `agon-mos-agondev` under the shared mystuff
parent and authorized a private GitHub repository of that name. The first
control includes only the existing recorded portability edits needed for the
clean official-source AgonDev build; no additional post-release behavior fix.

## Released first tranche

Create the private repository, preserve official source history and establish
the maintained native C/GNU assembly and direct build (B005-04). Review native
source readability and upstream/deviation maps (B005-05), checking conversion
and cleanup against the pinned translated AgonDev control with offline tests
(bounded B005-06). Promote reusable infrastructure only where needed for this
build (bounded B005-09). Stop before human emulator/hardware qualification,
release tagging, B005-07 qualified handoff or B005-08 EMOS adoption. Leave new
implementation changes available for review; initial guidance/contract dirt is
explicitly authorized for commit/push. Do not publish the new repository publicly.

## Policy and ownership agreement

1. [x] **B005-01** — Record the accepted toolchain, source-readability,
   traceability and Extender-first policy in current guidance. Preserve the
   distinction between accepted direction and qualified executable workflow.
2. [x] **B005-02** — Obtain explicit Extender-owner agreement on repository,
   agent, shared-contract and handoff boundaries. Publish the exact accepted
   contract and immutable message references. Route downstream guidance/task
   changes through the owner rather than editing their worktree unilaterally.
   Complete: Extender accepted v1 without amendments and confirmed direct
   agon-emos adoption ownership; foundation owner confirmed the clarification.
   Immutable references are recorded below and in the central topic index.

## Implementation and qualification

3. [x] **B005-03** — Resolve foundation repository identity/location and selected
   generic-fix baseline with the Author; obtain an implementation tranche.
   Preserve the current installed/accepted firmware and immutable comparison
   controls. Use persistent isolated workspaces before reviewed promotion.
   Complete: Author accepted `agon-mos-agondev` locally under mystuff, authorized
   private GitHub creation and the bounded first tranche stated above.
4. [ ] **B005-04** — Preserve official history and import provenance; establish
   the conversion-only native source and direct AgonDev build in the selected
   repository. Keep toolchain/runtime pins, conversion inputs and source maps.
5. [ ] **B005-05** — Review and improve native-source readability: recognizable
   modules/macros, descriptive private labels, native anonymous/macro-local
   idioms, focused upstream comments and a stable deviation register. Separate
   these edits from mechanical conversion and behavior fixes.
6. [ ] **B005-06** — Reproduce the selected translated AgonDev control or explain
   every difference with scripts. Qualify each cleanup, API/ABI expectations,
   startup/link/runtime contracts and relevant behavioral regressions. Preserve
   known tool limitations and respect human emulator/hardware gates.
7. [ ] **B005-07** — Deliver an immutable foundation selection and complete
   source/build/evidence handoff to the EMOS owner. Agree tag/release naming and
   adoption scope; no unqualified dependency change or automatic deployment.
8. [ ] **B005-08** — Support owner-reviewed EMOS adoption and reproducible native
   builds, preserving Extender behavior, history, source profiles, baud checks
   and product-owned tests. The EMOS owner tracks and performs its source work.
9. [ ] **B005-09** — Promote selected reusable comparison/provenance tools from
   BUILD-003/004 workspaces where needed for ongoing native maintenance. Keep
   one production authority per tool, preserve frozen evidence and leave vendor
   tool bytes outside Git. This carries forward their unfinished generic-tool
   promotion rather than pursuing ZDS-only compaction.
10. [ ] **B005-10** — After qualification/adoption, update actual onboarding and
    build instructions to native-source development; retain historical
    translation/reproduction support. Record acceptance/disposition and update
    the authoritative TODO. UART requires a separate future decision/task.

## Contract negotiation evidence

Thread: `mos-toolchain-size-matrix`, branch `native-foundation-v1` in the
central mailbox. Proposal message:
`2026-10-15_21-40-16_mos-agondev_native-foundation-contract-proposal-one`.
It replies to Extender's forwarded proposal
`2026-10-15_21-22-31_linux-extender_agondev-native-foundation-proposal-20261015-one`.
The topic index owns derived forward links and agreement status.

Extender acceptance:
`2026-10-15_21-52-47_linux-extender_native-foundation-contract-acceptance-one`.
Foundation-owner confirmation:
`2026-10-15_21-54-35_mos-agondev_native-foundation-contract-confirmed-one`.
No substantive amendments were requested. Downstream responsibility is assigned
to `linux-extender` within separately authorized scope; existing owner fences
are preserved. Agreement does not implement, qualify or release a new firmware.
