# BUILD-004 — MOS-family toolchain and UART size comparison

Compare the same stock MOS and EMOS foundations under ZDS II and AgonDev,
then measure the incremental cost of the same interrupt-driven UART0 addition
on each foundation. This separates toolchain costs, EMOS enhancement costs,
and UART integration costs. Two enhanced variants do not yet exist, so the
complete comparison requires reviewed porting and integration, not just builds.

Status: Stages 1–3 completed and published in `b9e957e`. The Author subsequently
selected the native AgonDev foundation and deferred UART on 2026-10-15.
Stage 4 is disposed as deferred, **not implemented or qualified**; UART may
never enter EMOS. No complete eight-combination matrix is claimed. The active
Extender-first transition is [BUILD-005](BUILD-005.md), governed by the
[native foundation policy](../native-foundation-policy.md), which supersedes
the earlier native-ZDS requirement. Results and qualification limits are in the
[comparison report](../../research/build-004-2026-10-15.md) and
[portable summary](../../evidence/build-004-summary.json).

`TODO.md` is the authoritative open-work index. Subtask IDs and explicit
numbers below are permanent; do not renumber or reuse them. Mark completion
or other disposition with `[x]` and record its evidence and rationale.

## Ownership and boundaries

mos-agondev owns this investigation, provenance manifests, reusable build and
comparison machinery, and the consolidated report. Product source and behavior
remain owned by agon-mos and agon-emos; Extender integration contracts remain
with agon-extender. Author approval of this plan must define the released
stages; mailbox replies are information, not implementation authority.

Use isolated persistent clones under the existing workspace parent described
in [BUILD-003](BUILD-003.md), with a distinct BUILD-004 inventory. Keep canonical
mos-agondev on main for task administration. Preserve existing work and frozen
artifacts. Promote maintained changes only after review into their owning
repositories; never promote hand-edited generated output as maintained source.

Read applicable repository instructions and the canonical environment/network
guidance before execution. Keep proprietary tool/runtime bytes outside Git.
No hardware access, flashing, reset, SD deployment, startup changes or emulator
changes are authorized here. Runtime qualification is a separate explicit gate.

## Evidence received and proposed source selection

The central mailbox is in agon-dev-env/cross-agent/agentcoms. Immutable replies:

1. `2026-10-15_17-48-46_linux-extender_emos-provenance-reply-20261015-one`
   confirms EMOS baseline, ancestry, existing UART scope and ownership constraints.
2. `2026-10-15_17-51-36_agon-mos_build003-uart-provenance-reply-one`
   supplies the UART snapshot, native build provenance and integration limits.

Both belong to thread `mos-toolchain-size-matrix`. After Author approval of the
concrete Stages 1–3 plan, replies were acknowledged and the released scope sent
to both owners in `2026-10-15_18-16-16_mos-agondev_build004-approved-tranche-one`
and `2026-10-15_18-16-17_mos-agondev_build004-approved-tranche-two`.
Re-read the mailbox before further execution for corrections; do not silently
change selected inputs.

| Variant | Exact proposed input | Current evidence |
| --- | --- | --- |
| Stock MOS | v3.0.2, `8336409351ee5314e02801a7b72a4f1bb5282519` | Common upstream foundation confirmed by both owners |
| EMOS | v0.1.24, `cf10f0b1848346bc5d04056e4663bbbc166b2480` | Installed AgonDev payload reproduced in BUILD-003; native baseline assessed |
| Stock + UART | Frozen ABI1.2 full-integration snapshot below | Native ZDS candidate retained; no AgonDev port/build supplied |
| EMOS + UART | Same selected UART revision adapted to pinned EMOS | Does not exist; integration and qualification pending |

EMOS identity: `agon-emos-v0.1.24-b2026-10-07-23-11-33Z`.
Installed payload: 128,622 bytes, SHA-256
`44d217b555f68a7d030bc0a89a2fa1d27f0fb537576f2925e90ef055b0a44d02`.
Its 2,450-byte free tail is **EMOS**, not stock MOS, headroom.

UART owner repository: bgates747/agon-mos, branch `codex/uart0-async`, reported
HEAD `0e019586788922b13852d0760f96c7d391561b39`. HEAD alone is not the firmware
receipt: use the frozen archive and verify its manifest against source history.
Paths in this paragraph are relative to the sibling agon-mos repository:

1. `build/uart0-mos/source.tar`, SHA-256
   `38321531d35faff356b065daab1b4ac64dea9a4acb4e3d1e0b72177937dacc9f`.
2. Source manifest SHA-256
   `580807d7b83846be0535e5dfe467e39eb92d02ec050437f7e660f07bc914eebf`.
3. Retained `MOS.bin`: 111,063 file bytes, SHA-256
   `9a523c0fb7655e46297a5bc7586e53f9fdb536244f3407a265e87ce17f1cd907`.
   This is an input to verify, not a fresh reproduction or consistent-extent result.
4. `MOS.map`, `MOS.hex`, `build.log`, `logs/`, `tools.sha256`, listings and
   `artifacts.tar` provide native OMF695/HEX evidence, not a GNU ELF.

Author-approved tranche feature selection: ABI1.2, native OTIRX
path enabled, session batching controls 1/2/4/8/16 compiled in, default batch 1.
The earlier physically tested API1.1 sender is a different scope. Historical
`experiments/uart0-mos/results.json` describes its 110,695-byte build, not the
111,063-byte candidate. ABI1.2 is experimental, not installed/production-qualified.

The 2,497-byte uart0_async module contribution is **not** a whole-image feature
delta; it excludes hooks elsewhere. Initial owner mail described 86 BSS bytes
plus wrapper state; measured layout confirms 86 **total**, including the
one-byte wrapper synchronization depth. Borrowed payloads are not copied into a new ROM/RAM
payload buffer. Verify total RAM layout rather than assuming spare capacity.

## Comparison contract

Four source variants, each built under both toolchains, form the primary
matrix. Measure ZDS speed-oriented and size-oriented profiles separately for
each row: the retained stock-UART build uses speed optimization, while the
smaller native EMOS assessment uses size optimization. Never present those
unmatched settings as a controlled feature delta.

Pin tool executables, vendor headers/runtime libraries, Wine/launcher identity,
builder revision, per-file flags, source profiles, identity defines, generated
source and all compatibility patches. Reuse BUILD-003 pins only after verifying
them. AgonDev uses the retained Clang/runtime configuration with the ff.c -Os
exception unless an explicitly labelled experiment requires another profile.
Identity strings must match across toolchains within each variant; record any
unavoidable identity cost between variants. Report formatter feature policy
explicitly: identical source does not imply identical runtime-library features.

Report actual ROM extent against 131,072-byte capacity, load bytes, holes,
reserved regions, alignment/padding, initialized-data ROM copies, code,
constants, runtime libraries and RAM usage separately. Keep over-capacity
results useful for analysis but label them non-installable. Do not remove
features, relax linker guards, or claim behavior parity merely because a link
succeeds. Measure UART cost as enhanced minus matching baseline under the
same toolchain, optimization profile and product configuration. Measure EMOS
cost similarly against stock; rank module contributors and explain residuals.

BUILD-003 shared-printing/literal-pooling ZDS experiments are separate labelled
configurations, not the ordinary ZDS baseline. Reuse their evidence without
claiming runtime qualification or silently incorporating optimizations.

## Stage 1 — Freeze and validate provenance

1. [x] **B004-01** — Obtain Author approval of stage scope and ABI1.2 selection;
   reconcile open owner questions and then acknowledge/reply to mailbox messages
   with the agreed concrete plan. Preserve immutable references.
2. [x] **B004-02** — Inventory isolated workspaces, verify source/archive hashes,
   common upstream ancestry and snapshot-versus-commit differences. Record all
   patches and prevent contamination by unrelated diagnostic/test changes.
3. [x] **B004-03** — Freeze compiler, library, header, launcher and build profiles;
   fill missing UART vendor-runtime/Wine receipts. Define deterministic identity,
   accounting and artifact manifests before comparisons.

## Stage 2 — Measure both foundations

4. [x] **B004-04** — Build/reproduce stock MOS under AgonDev and native ZDS speed
   and size profiles. Retain commands, return codes, maps, objects, assembly or
   listings, hashes and accounting reports.
5. [x] **B004-05** — Reuse verified EMOS AgonDev and native-size results from
   BUILD-003 where controls match; reproduce native-speed and any missing or
   mismatched controls. Record the two native C compatibility edits explicitly.
6. [x] **B004-06** — Publish the foundation comparison with common accounting,
   per-module attribution, formatter-policy limits and unexplained differences.

## Stage 3 — Measure stock MOS plus UART

7. [x] **B004-07** — Reproduce the frozen stock-UART native candidate under its
   original settings, then add the matched size-profile measurement. Verify the
   original binary or explain drift before interpreting deltas.
8. [x] **B004-08** — Port that same source snapshot to AgonDev in isolated owned
   workspaces. Keep generic translator/preparation changes separate from product
   changes; test new syntax/ABI handling rather than globalizing local labels.
   Preserve the full selected UART behavior and record compatibility patches.
9. [x] **B004-09** — Measure matched stock-to-UART ROM and RAM deltas for each
   configuration. Run authorized offline static/unit/ABI checks, explicitly
   separating build validity from emulator/physical qualification.
10. [x] **B004-10** — Present Stages 1–3 results and limitations to the Author;
    pause for a separate Stage 4 decision. No toolchain-policy change is inferred.

Completed-stage evidence: report sections 1–3 cover B004-01 through B004-07;
sections 3–4 cover B004-08 and B004-09; sections 5–6 and the review handoff cover
B004-10. No new translation/source patches were required for B004-08: the
existing extra-assembly profile builds the frozen candidate. Eleven comparison,
seven diagnostic-mapping and four profile checks pass. The stock frontend
suite retains one objdump-display failure (23/24 pass); its stock-only corpus
assertion also cannot be used unchanged for UART's 16-unit fixture. These are
recorded limits, not a successful full-suite claim. No runtime gate is closed.

## Stage 4 — Deferred EMOS UART integration and comparison

The items below are marked disposed, not completed implementation. Releasing
UART integration later requires a new explicit decision and owning task; they
are not a prerequisite for the foundation or EMOS transition.

11. [x] **B004-11** — After separate authorization, agree owner-reviewed EMOS
    integration design and source fences. Start with Legacy routing; preserve
    EMOS ownership and refuse unsupported async sessions on other routes rather
    than bypassing EMOS. Preserve UART1 input/SD/console, admission, recovery,
    interrupt state, blocking barriers and application-return fencing.
    Disposed: UART integration design deferred by the Author.
12. [x] **B004-12** — Integrate the selected UART revision in an isolated EMOS
    clone, retaining discovery/ABI, three-slot borrowed-source queue, session
    policy/reset, single UART0 TX/RX owner, existing receive parser, per-byte
    legacy writes, masked-IFF pumping and callback/source-lifetime constraints.
    OTIRX remains bounded CPU block I/O, not DMA: maximum 16 writes per service
    opportunity, CTS checked before each block, source/budget bounds preserved.
    Disposed: no EMOS UART integration performed; future inclusion undecided.
13. [x] **B004-13** — Build the identical integrated EMOS source under both
    toolchains and native profiles. Report integration replacement/addition
    costs, RAM constraints, failed links and adaptation differences separately.
    Do not silently extract diagnostics or cut features to fit.
    Disposed: absent integration remains unmeasured; no estimated row promoted.
14. [x] **B004-14** — Consolidate the complete matrix and recommend next steps.
    Promote reviewed reusable tools/evidence here, route maintained product
    changes to owners, record qualification still required and obtain Author
    disposition before updating the authoritative TODO.
    Disposed: bounded Stages 1–3 report published; partial matrix retained;
    generic-tool promotion carried to B005-09 and UART work deferred.

## Acceptance

Each released stage must leave script-reproducible provenance and measurements,
consistent accounting, clearly bounded unknowns and an explicit review handoff.
The complete matrix requires eight source/toolchain combinations plus separately
identified optimization controls; absent integrations must be shown as absent,
not estimated results. Runtime acceptance, production promotion and toolchain
selection remain separate Author decisions. Initial registration was
documentation-only; subsequent approval released Stages 1–3 as stated above.
Author separately authorized publication of the analysis in `b9e957e`.
No source promotion, runtime acceptance or Stage 4 implementation was authorized.
