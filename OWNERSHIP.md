# Repository ownership

This repository is the reusable AgonDev build and qualification environment
for maintained ZDS-oriented MOS-family source. It is not a MOS product fork.

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
3. A one-time source portability exception belongs in the exact, fail-closed
   preparation profile for that input; an ongoing ZDS language feature belongs
   in the translator with semantic and diagnostic tests.
4. Candidate-only command, ABI, media, or hardware expectations must be passed
   through `SOURCE_PROFILE`, another explicit option, or a reviewed fixture.
   Do not hard-code one product's vocabulary into generic comparison machinery.
5. Generated output is evidence only and must never be hand-edited to alter
   maintained behavior.
