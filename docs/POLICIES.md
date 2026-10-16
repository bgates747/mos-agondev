# MOS project policies

MOS-family development uses readable native source, coordinated canonical API
definitions and reproducible firmware identity. This document is the single
project policy authority for the foundation and its reusable infrastructure.
Consumer projects follow the shared API rules without acquiring authority to
change another owner's source, installed firmware or release selections.

The native-source direction was accepted on 2026-10-15; canonical interfaces,
identifier reservations and build identity were accepted on 2026-10-16.
Accepted policy is not a claim that its implementation is complete.

## Policy authority and document roles

1. This document owns project-wide toolchain, maintained-source, API allocation,
   build-identity and qualification policy. Onboarding and agent handoffs link
   here; their summaries do not establish competing policy.
2. [OWNERSHIP.md](../OWNERSHIP.md) defines repository routing, and the
   [central contract](../../agon-dev-env/cross-agent/mos_agondev_foundation/CONTRACT.md)
   owns the mutually accepted cross-owner agreement. These remain separate
   authorities for their stated purposes; consolidation does not silently amend
   that agreement or transfer product ownership.
3. Technical specifications describe executable contracts. In particular,
   [assembly compatibility](assembly-compatibility-strategy.md) governs the
   retained translation pipeline, not the future native source of truth.
   Research, mailbox messages and dated logs preserve evidence and decisions;
   they are not alternative current policy or task lists.
4. [TODO.md](../TODO.md) is the authoritative unfinished-work index. Native
   migration remains BUILD-005; canonical API/build-identity implementation is
   tracked as API-001. No firmware, SDK or consumer changes are implemented by
   adopting this policy document.

## Native source and toolchain direction

AgonDev is the accepted toolchain for the future maintained MOS foundation and
EMOS development. The foundation will be a separate, human-maintained fork of
official MOS, with C and GNU assembly edited directly. Extender requirements
drive active EMOS work; stock-foundation maintenance follows reviewed upstream
changes and generic fixes. UART integration into the starting foundation and
EMOS is deferred and is not a prerequisite for this transition. Separately
authorized experimental UART work does not change that boundary. The qsort API
experiment is excluded; it is not a foundation or UART prerequisite. Existing
internal sorting is unaffected.

Status: accepted by the Author on 2026-10-15. This decision supersedes the
earlier requirement to make native ZDS II the EMOS release toolchain. It does
not change the installed firmware or qualify a new source tree. Migration is
tracked in [BUILD-005](tasks/BUILD-005.md); current executable build instructions
here still describe the retained translation pipeline. The first direct native
candidate has its own setup instructions and offline evidence in private
`bgates747/agon-mos-agondev`; it is not yet qualified or adopted by EMOS.

## Repository and agent responsibilities

The cross-project ownership and handoff authority is the
[foundation contract](../../agon-dev-env/cross-agent/mos_agondev_foundation/CONTRACT.md).
Contract v1 was explicitly accepted by both participants on 2026-10-15;
its agreement does not itself authorize implementation or adoption.

1. mos-agondev retains reusable compiler, linker, runtime, comparison,
   provenance and qualification machinery. Its agent leads the generic native
   foundation migration and qualification in a separate maintained-source
   repository, not in disposable build directories.
   The Author selected `bgates747/agon-mos-agondev` as the private foundation
   repository, at `../agon-mos-agondev/` relative to this repository root.
2. agon-emos retains EMOS source, behavior, APIs, Extender-specific changes,
   source profiles, product checks and release evidence. Downstream adoption
   must retain its history and product requirements; it is not a wholesale
   replacement of EMOS with stock MOS.
3. agon-extender retains assembled-product architecture, EDP/P4 firmware,
   wiring, transports, modes and system qualification. Its agent
   `linux-extender` directly handles downstream agon-emos adoption/implementation
   within separately authorized scope, preserving existing work and owner fences.
4. Official MOS/VDP reference checkouts remain read-only. The existing
   UART-oriented working fork is not repurposed into the new foundation.

## Source readable by maintainers

The maintained fork is source for people, not a frozen dump of converter output.
Use the converter to establish a measured starting point; review and explicitly
promote source into the new repository before editing it as maintained code.
Existing `worktree` and `generated` directories remain disposable.

1. Preserve official source history, release ancestry, file and function names,
   directory layout, explanatory comments, authorship and license notices
   wherever practical. Use a distinct conversion commit; avoid mixing
   reformatting, behavior changes and dialect conversion in one patch.
2. Retain recognizable subroutines and macros. Reconstruct readable native GNU
   macros where conversion expanded them, with separate equivalence checks.
   Do not make hundreds of repeated expansions the routine maintained form
   merely because the generator emitted them.
3. Use descriptive local names and GNU's native anonymous/macro-local idioms
   where they express the original intent. Procedure-specific private names
   such as `.Lroutine_done`, numeric `1f`/`1b` targets, and unique macro-local
   labels are appropriate. Preserve binding and scope intent; do not
   gratuitously export locals or retain opaque generator identifiers as the
   default source vocabulary. GNU `.L` binding alone does not recreate ZDS
   procedure scope: repeated named locals require deliberate disambiguation.
4. Keep an upstream-to-native file and symbol mapping. A reader must be able
   to identify the official release/commit, corresponding upstream path and
   routine, and reason for any local divergence without reconstructing chat
   history or reverse-engineering generated names. Store paths relative to
   repository roots, not a developer's home directory.
5. Record each meaningful deviation under a stable identifier: upstream
   origin, change category, reason, evidence, affected contracts, qualification
   and removal condition. Categories include mechanical syntax conversion,
   compiler/ABI portability, inherited defect correction and intentional
   behavior change. Separate EMOS product deviations from generic foundation
   deviations. The register explains maintained differences; actionable work
   stays in the owning TODO and task details.
6. Put the explanation beside unusual code as well as in the deviation
   register. Explain what upstream did, why the local form is necessary and
   what would allow its removal. Unchanged C need not acquire boilerplate
   provenance comments; a file manifest plus focused comments at real changes
   provides traceability without obscuring the code.
7. Avoid gratuitous algorithm, API or layout changes during conversion. In
   particular, keep fixes separate from the clean official-source control.
   Any deliberate instruction/data change needs reviewed evidence, not a
   claim that a new spelling is necessarily equivalent.

## Qualification and downstream handoff

The first foundation starts from pinned official MOS v3.0.2 commit
`8336409351ee5314e02801a7b72a4f1bb5282519`, without experimental UART additions.
Repository identity is accepted; any subsequent generic-fix selection remains
explicit. Existing translated AgonDev output supplies
the conversion reference; ZDS supplies upstream comparison evidence.

The conversion-only build must reproduce the selected AgonDev reference bytes
or account for every difference, including metadata, layout and relocations.
Readability cleanups and macro reconstruction are separately reviewed and
qualified. Binary identity checks do not replace API/ABI, behavioral or physical
timing checks. Known disassembler defects must not be used to dismiss actual
encoding differences.

The foundation owner hands off an immutable commit/tag, exact tool/runtime
selection, reproducible build recipe, source and deviation maps, firmware and
ELF/map/hash evidence, and the qualification scope and remaining gaps. A tag
does not itself make a release accepted. The EMOS owner reviews that exact
selection, ports its maintained enhancements without discarding lineage, and
retains product-specific linked-image invariants, including baud/divisor
checks. No dependency update silently advances an EMOS foundation pin.

Human emulator validation, hardware qualification, release naming, deployment
and publication retain their existing explicit gates. The policy and contract
do not independently authorize bench access, flashing or installation.

## Development after adoption

Maintainers edit native C/GNU assembly directly and build with AgonDev. Routine
builds do not regenerate maintained source from a second ZDS copy. Historical
translation machinery remains available for reference, migration and upstream
comparison; it is not the future source of truth.

When upstream MOS changes, the foundation owner reviews the selected release
delta against recorded ancestry, ports the relevant changes, refreshes mappings
and deviations, and qualifies the new pin. The EMOS owner then reviews adoption
against its product changes and requirements. Generic fixes discovered during
EMOS development follow the same owner-reviewed path into the foundation;
Extender-specific behavior stays in agon-emos. This does not require continual
stock-MOS feature development unrelated to upstream or EMOS needs.

ZDS II remains useful for building and inspecting upstream source; maintaining
two authoritative assembly dialects or requiring ZDS to build the native fork
is not part of this model. Promoting source does not itself save additional ROM
beyond the measured AgonDev build. UART remains a separate experimental project
and may never be merged into EMOS.

## Canonical API definitions and reservations

1. The official MOS `src/mos_api.inc` and AgonDev `<agon/mos.h>` are the
   canonical assembly and C/C++ interfaces. The older `<mos_api.h>` name is a
   compatibility entry point, not a separately maintained interface.
   Assembler-specific bindings must preserve
   the same allocated values and ABI; differing syntax does not permit a
   different allocation authority.
2. All projects consume the selected, versioned canonical interface files
   directly from the shared interface distribution or dependency. Do not
   manufacture or hand-maintain project-local variants, redefine numbers in
   application code, or copy a header and let it drift. Mechanically generated
   language/dialect bindings may be distributed with provenance and consistency
   checks; they are not independent sources of definitions.
3. Projects needing a carveout reserve it in the canonical allocation list
   before introducing a call or publishing a consumer. Record namespace,
   numeric identifier/range, symbolic name, owner, purpose, ABI/version and
   status: reserved, experimental, accepted or retired. Maintain this list
   alongside the canonical definitions, or in their single shared source from
   which bindings are generated. A separate unverified list is not authority.
4. MOS call numbers dispatched through RST08 and indices selected through
   `mos_getfunction` are separate namespaces. Identify the namespace explicitly
   in every reservation, include definition, test and review. Versioned
   extension tables also document their own operation/field layout.
5. Coordinate allocations across upstream MOS, the native foundation, EMOS and
   experimental variants through the foundation/interface owner and affected
   project owners. Preserve upstream assignments. A local reservation is not
   an upstream official allocation; any upstream collision requires explicit
   resolution before adoption. Do not silently reuse an experimental/retired
   identifier or renumber an established consumer-facing entry.
6. Experimental status remains visible in definitions and capability discovery.
   No experimental feature becomes accepted merely because its constant exists.
   The excluded qsort experiment is not an API requirement. The previously used
   experimental UART getfunction index0x13 must not silently be renumbered;
   omitting qsort does not grant a new assignment of slot0x12.
7. Changes to the interface distribution, SDK bindings or consumer projects
   follow their owners' review boundaries. These policies do not authorize
   editing upstream reference checkouts or bulk replacement of consumers.
   Physical packaging and automated collision checks remain implementation work.

## Firmware and interface build identity

1. Every firmware build supplies version information through its canonical
   interfaces: the exact MOS/product version numbers and identity shown in
   boot banners, the full firmware source commit hash, a dirty-tree indicator,
   and a separately identifiable API-definition version/revision. Include the
   selected interface-source revision when it differs from firmware source.
2. Generate one build-identity record per firmware build and use that same
   record for firmware banner construction and the distributed C/C++ and
   assembly interfaces. A generated metadata include imported by the canonical
   files is acceptable; manually maintaining independent banner/header values
   is not. Application builds consume the selected record without rewriting
   shared definitions or changing the firmware identity.
3. The commit hash identifies the source revision being built, not a fabricated
   hash of a commit that would contain its own generated hash. Dirty builds
   remain explicitly dirty; a clean HEAD hash alone cannot identify their full
   contents. Preserve actual source-content hashes in build provenance and
   reject unknown identities for accepted release artifacts. Do not silently
   substitute another checkout's HEAD or an unpinned dependency revision.
4. Distribute the matching interface files and identity record with each
   firmware build so new projects select them together. Record/pin the selected
   dependency in consuming builds. Availability of a new build does not
   silently upgrade existing consumers or qualify a product dependency update.
5. Compile-time metadata says what an application was built against, not what
   firmware is installed. Runtime version/capability discovery remains the
   authority for invoking optional features; retain graceful fallback. A new
   runtime identity query, if needed, requires its own coordinated API design
   and reservation rather than an invented number in a local header.
6. Acceptance checks must demonstrate agreement between banners, metadata and
   both language bindings, correct dirty handling, deterministic generation
   from the same selected inputs, and absence of allocation conflicts or stale
   copied definitions. Defining this policy does not assert that those checks,
   interface distribution or runtime discovery enhancements already exist.
