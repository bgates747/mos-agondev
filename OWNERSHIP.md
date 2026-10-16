# Repository ownership

This repository is the reusable AgonDev build and qualification environment
for MOS-family source. Its currently implemented pipeline accepts maintained
ZDS-oriented source; the accepted native-foundation transition is described in
[project policies](docs/POLICIES.md). It is not a MOS product fork.

The mos-agondev agent leads generic native-foundation migration/qualification
in a separate firmware repository. That responsibility does not transfer
maintained source into this infrastructure repository or give it ownership of
EMOS product behavior. The
[central contract](../agon-dev-env/cross-agent/mos_agondev_foundation/CONTRACT.md)
governs cross-owner handoff; implementation remains in the owning repositories.

## This repository owns

1. Prepared-worktree generation with exact drift checks.
2. ZDS-to-GNU-as translation and its supported-language contract.
3. AgonDev compilation, linker layout, restricted runtime support, and generic
   C/assembly ABI probes.
4. Generic emulator profile generation, stock/candidate comparison, source
   auditing, regression harnesses, and qualification infrastructure.
5. Tasks and evidence concerning those reusable capabilities.

## This repository does not own

1. Official or customized maintained MOS source.
2. EMOS behavior, APIs, module/service policy, operating modes, product tasks,
   or release qualification.
3. Extender EDP firmware, physical transport, carrier wiring, or assembled
   product architecture.
4. Generated prepared source, translated assembly, objects, maps, firmware,
   emulator profiles, or staged media as maintained source.

## Neighboring repositories

1. `agon-mos` is the Author's upstream-oriented official-MOS fork.
2. `agon-emos` owns the complete maintained EMOS source and all EMOS-specific
   contracts, tooling, tests, tasks, and qualification evidence.
3. `agon-extender` owns cross-component Extender architecture, hardware,
   transports, operating modes, and system qualification.

## Change routing

1. A change applicable to every supported MOS-family source belongs here.
2. A source-specific behavior change belongs in that source repository.
3. In the existing translation pipeline, a one-time source portability
   exception belongs in the exact, fail-closed preparation profile; an ongoing
   ZDS language feature belongs in the tested translator. After native adoption,
   maintained-source portability changes belong in the foundation or product
   source with provenance and reasons, not a hidden regeneration pass.
4. Candidate-only command, ABI, media, or hardware expectations must be passed
   through `SOURCE_PROFILE`, another explicit option, or a reviewed fixture.
   Do not hard-code one product's vocabulary into generic comparison machinery.
5. Generated output is evidence only and must never be hand-edited to alter
   maintained behavior. Native migration explicitly reviews/promotes source
   into a separately maintained tree; it never changes the ownership of an
   existing disposable `worktree` or `generated` directory by implication.
