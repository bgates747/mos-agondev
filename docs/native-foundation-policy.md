# AgonDev native MOS foundation and EMOS development

AgonDev is the accepted toolchain for the future maintained MOS foundation and
EMOS development. The foundation will be a separate, human-maintained fork of
official MOS, with C and GNU assembly edited directly. Extender requirements
drive active EMOS work; stock-foundation maintenance follows reviewed upstream
changes and generic fixes. Experimental UART work is deferred and is not a
prerequisite for this transition.

Status: accepted by the Author on 2026-10-15. This decision supersedes the
earlier requirement to make native ZDS II the EMOS release toolchain. It does
not change the installed firmware or qualify a new source tree. Migration is
tracked in [BUILD-005](tasks/BUILD-005.md); current executable build instructions
still describe the existing translation pipeline until the new native build is
qualified and adopted.

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
