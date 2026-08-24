# Generic PORT-200 qualification record

The PORT-200 effort expanded this repository's reusable MOS-family port and
qualification infrastructure. EMOS product contracts, fixtures, hardware gate,
and release evidence moved to the `agon-emos` repository; this document records
only the retained generic results.

## Retained capabilities

1. Candidate/reference shell parity uses bounded emulator processes, isolated
   temporary hostfs roots, exact fixture snapshots, and explicit candidate-only
   HELP additions supplied as arguments rather than hard-coded vocabulary.
2. Linked VDP parser qualification covers idle noise, corrupt-state recovery,
   legal lengths 0–16, partial bodies, oversized lengths 17–255, General Poll
   recovery, and a bounded instruction budget. Physical timing remains outside
   emulator evidence.
3. The target ABI probe covers read and write paths, two-cold-boot persistence,
   cleanup, wrapper layout, high-byte values, and documented Fab limitations.
4. Emulator profiles use a generated, directly invoked project-local launcher
   and a separate raw Fab binary link. Setup and verification reject obsolete
   or drifted layouts.
5. Baseline schema 2 pins public source identities and stock firmware artifacts
   while excluding path-dependent locally compiled Fab executable bytes.
6. Source auditing ignores untracked products and submodule dirt but rejects
   tracked input changes. The generic oversized-packet source correction is
   independently maintained in `agon-mos`.

## Ownership boundary

This record does not claim EMOS behavior, module ABI, mode operation, EDP
transport, or physical EMOS qualification. Those authorities live in
`agon-emos` and `agon-extender`. The generic tools accept candidate-specific
expectations only through explicit options or reviewed profiles.

The maintained product-profile interface currently accepts additional C source
units, their corresponding runtime objects, and reviewed candidate-only HELP
commands. The source repository owns the profile and its tests.
