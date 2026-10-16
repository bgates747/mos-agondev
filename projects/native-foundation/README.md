# Native foundation build and migration tools

These tools support human-maintained C/GNU assembly, not a second generated
source workflow. Normal builds compile the selected native repository directly.
The initial migration is deliberately pinned and separate; binary equivalence
is offline evidence, not runtime acceptance or authorization to deploy.

## Responsibilities

1. `migrate.py` is a **one-time migration tool** for a clean official MOS
   v3.0.2 checkout at `8336409351ee5314e02801a7b72a4f1bb5282519`.
   It reuses the existing corpus-driven frontend and exact preparation edits,
   converts each original assembly/include file separately, and preserves
   macros/includes. `--readable` replaces generator names with descriptive
   private labels and native anonymous/macro-local idioms. Both modes emit
   file, line, symbol and macro mappings. It requires a fresh destination;
   never point it at the maintained native repository.
2. `build.py` consumes the native repository's explicit `build.json` source
   inventory, order, optimization exceptions and product-owned linked-image
   checker list. It invokes neither migration nor translation. It reuses the
   existing restricted runtime, target provenance and firmware/link guards.
   Each invocation needs a fresh output directory, retains failed runs, hashes
   source/tool/helper inputs, and records actual target commands and dependencies.
   Every declared product checker must run successfully against the final ELF.
3. `compare.py` requires exact ROM bytes and defined public symbol names,
   addresses and kinds to match the selected control. Private ELF/debug symbols
   can differ; ELF hashes are reported rather than required to match. Empty,
   malformed or duplicate public-symbol records fail. This comparison never
   masks unexplained bytes as probable pointers.

The build helper accepts the pinned compiler/runtime documented by the source
repository. It checks overlapping hardware aliases against the SDK, runtime
closure, i48 helper equivalence, formatter usage/golden cases, and final image
layout. A product profile cannot silently suppress a declared checker failure.
Changing toolchain/runtime, source composition or qualification is reviewed work.

## Invocation

Run from the mos-agondev root using its project interpreter, supplying your own
dependency locations. No common parent-directory layout is required:

```bash
.venv/bin/python projects/native-foundation/migrate.py \
  --upstream PATH_TO_CLEAN_PINNED_OFFICIAL_MOS \
  --destination PATH_TO_FRESH_MIGRATION_WORKSPACE --readable

.venv/bin/python projects/native-foundation/build.py \
  --source-root PATH_TO_NATIVE_SOURCE --toolchain PATH_TO_AGONDEV_RELEASE

.venv/bin/python projects/native-foundation/compare.py \
  --native-bin-dir PATH_TO_NATIVE_RUN_BIN \
  --reference-bin-dir PATH_TO_PINNED_TRANSLATED_CONTROL \
  --nm PATH_TO_AGONDEV_RELEASE/bin/ez80-none-elf-nm \
  --output PATH_TO_COMPARISON_JSON
```

Prefer the native source repository's root `make firmware-check` for normal
development. Optional `--reference-bin` adds a pinned migration-byte gate to
the direct helper; it is not the normal gate for intentional source changes.
There is no incremental-build or cleanup/deployment routine in this first pass.

The maintained foundation is private `bgates747/agon-mos-agondev`. Its
`STARTHERE.md`, upstream origin, deviation register and source-owned tests are
authoritative for editing firmware. Coordination and qualification boundaries
remain in [BUILD-005](../../docs/tasks/BUILD-005.md); the first-tranche result is
in [the dated research report](../../research/build-005-2026-10-15.md).
