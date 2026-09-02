# Start here: developing MOS with AgonDev

This repository uses **ZDS-oriented source as maintained source** and
AgonDev-compatible source as disposable build output. Do not hand-edit the
generated GNU-as files.

> **Important compatibility limit:** `zds2gas.py` is not a complete ZDS II
> assembler, nor was it built from an exhaustive survey of every ZDS II
> directive, convention, or idiom. Its accepted language is the subset found
> in the maintained MOS corpus plus a small number of explicitly tested public
> include constructs. Existing MOS building successfully proves that corpus,
> not arbitrary ZDS II source. A newly introduced ZDS construct may therefore
> be rejected and must not be assumed compatible merely because ZDS II accepts
> it.

All commands below run from the `mos-agondev` repository root. The recommended
layout keeps optional dependency checkouts inside ignored project-root
directories, but every setup script also accepts an explicit path.

## 1. Create the Python environment

Python 3.14 or newer is required by `pyproject.toml`. The project currently uses
only the Python standard library. In these examples `python3.14` means any
executable that reports Python 3.14 or later. Verify the specific interpreter
used to create the environment; an unqualified `python3` may be older:

```bash
python3.14 --version
python3.14 -m venv .venv
```

There is no package-install step. Activating the environment is optional;
project commands name `.venv/bin/python` explicitly.

If `python3.14` is unavailable, install Python 3.14 or use the equivalent
versioned executable for your platform. Do not create the environment with an
older interpreter: `scripts/verify_environment.py` rejects it explicitly.

## 2. Provide AgonDev and MOS source

The default self-contained layout is:

```text
mos-agondev/
├── agondev/        # checkout with a built release/ tree
└── agon-mos/       # writable maintained-source worktree
```

This firmware port currently accepts AgonDev source commit
`b67ab2444a63267a42193f204889d466765d8dd2` (tag `nightly`) and the matching
built `release/` tree. The C/header contract pins that commit, and the runtime
contract pins its `release/lib/libagon.a`; another release is an intentional
toolchain-upgrade task, not a drop-in input. Build that checkout according to
its upstream instructions (`make_tools.sh`, then the AgonDev library build),
and put it at `agondev/`. A project-root source build is:

```bash
git clone https://github.com/AgonPlatform/agondev.git agondev
git -C agondev checkout b67ab2444a63267a42193f204889d466765d8dd2
(cd agondev && ./make_tools.sh)
make -C agondev clean
make -C agondev all
```

The tool build is substantial; consult `agondev/README.md` for its host
prerequisites and resource requirements. Put the `agon-mos` checkout or
developer worktree you intend to maintain at `agon-mos/`.

Then create the ignored project links:

```bash
.venv/bin/python scripts/setup_local.py
```

For dependencies elsewhere, supply both locations explicitly:

```bash
.venv/bin/python scripts/setup_local.py \
  --agondev PATH_TO_AGONDEV \
  --agon-mos PATH_TO_AGON_MOS
```

`setup_local.py` validates the toolchain and source shape before creating
relative `toolchains/agondev` and `upstream/agon-mos` links. It does not modify
either input and refuses to replace an unexpected existing path.

The generic public baseline and its official v3.0.2 parent are recorded under
`evidence/` and documented in `docs/port-200-qualification.md`. Product source
repositories such as `agon-emos` own their own revision pins, additional source
files, behavioral expectations, and release evidence. This repository accepts
those inputs through the same maintained-source boundary rather than embedding
their product history.

## 3. Optionally install Fab Agon Emulator

Fab is not needed for translation, compilation, linking, or
`make firmware-check`. It is required for emulator setup, boot/parity/contract
checks, graphical testing, and complete `make verify`.

The recommended location is the ignored `fab-agon-emulator/` directory in this
repository. To build the pinned 1.2.3 release from source, first install Fab's
documented prerequisites: Git, Make, Rust/Cargo, a C++ toolchain, and SDL3 plus
its development headers. Then run:

```bash
git clone --recurse-submodules --branch 1.2.3 --single-branch \
  https://github.com/tomm/fab-agon-emulator.git \
  fab-agon-emulator
make -C fab-agon-emulator
```

Fab's `fab-agon-emulator/docs/compiling.md` is authoritative for
platform-specific prerequisites.
A complete prebuilt Fab distribution may be unpacked at
`fab-agon-emulator/` instead. Whether built or unpacked, the directory must
contain:

- an executable `fab-agon-emulator` at its root or under `target/release`;
- an executable `agon-cli-emulator` at its root or under `target/release`;
- `firmware/mos_platform.bin`, `firmware/mos_platform.map`, and
  `firmware/vdp_platform.so`;
- populated `sdcard/bin`, `sdcard/mos`, `sdcard/MOS.bin`, and
  `sdcard/firmware.bin` inputs.

Create the separate ignored runtime profile only after those inputs exist:

```bash
.venv/bin/python scripts/setup_emulator.py
.venv/bin/python scripts/verify_emulator.py
```

`fab-agon-emulator/` is the source checkout or distribution. `emulator/` is a
generated writable profile with a mandatory direct launcher
`fab-agon-emulator` and a separate raw `fab-agon-emulator.bin` link; they are
not the same directory. The launcher supplies the local SDL3 path and selects
this project's candidate MOS. `setup_emulator.py` validates and profiles Fab
but does not download or build it.

For a complete Fab installation elsewhere, export one consistent override for
the shell session before setup or any later emulator-related Make target:

```bash
export FAB_ROOT=PATH_TO_FAB
make setup-emulator
make verify
cd emulator
./fab-agon-emulator
```

Alternatively prefix each command with `FAB_ROOT=PATH_TO_FAB`. The generated
profile remembers its symlink targets, but Make does not persist a prior
command-line variable.

## 4. Prepare and build for the first time

Create the ignored prepared source tree and build the firmware:

```bash
.venv/bin/python scripts/prepare_mos_worktree.py
make firmware-check
```

Preparation copies only Git-tracked MOS files and applies exact,
drift-checked initial portability edits. The firmware build automatically runs
the assembly compatibility frontend, assembles its generated units, links the
runtime, and verifies the image.

For a bounded product experiment that must not replace the current prepared
tree, pass explicit `--upstream` and `--destination` paths to preparation and
the same source and destination as `MOS_MAINTAINED_SOURCE` and `MOS_WORKTREE`
to every repository-root Make target. The root `worktree-check` validates that
exact pair before compiling; it never substitutes the default stock source or
prepared tree for a caller-selected product input. Named `worktree-*`
directories under `projects/mos-port` are ignored disposable outputs; record
the maintained source identity and exact preparation command in the owning
product task.

If Fab is installed and profiled, run the complete configured-input gate with:

```bash
make verify
```

### Optional actual-step provenance

Supply a new path, or an existing empty real directory, to capture one fresh
target-build session:

```bash
make firmware-check PROVENANCE_DIR=/absolute/path/to/new-evidence-directory
```

The repository-root target refuses a nonempty or symlink-aliased provenance
directory before cleaning build outputs. In provenance mode every target C
compile, wrapped or direct target assembly, and the final firmware link refuses
stale outputs and records the actual argv and working directory using stable
`BUILD_TOOL`, `BUILD`, `PREPARED`, `TOOLCHAIN`, `PYTHON_ENV`, and
`PROVENANCE` placeholders. `PYTHON_ENV` separates the ignored virtual
environment and its interpreter symlink from the tracked build-tool root.
In argv and transcript text, substitution selects the longest declared
lexical or resolved root at an exact-root, descendant-path, or conservative
compiler-text delimiter boundary. A declared root that is only a prefix of a
longer path component is not substituted.
Each record binds the recorder; executable and declared nested-tool hashes and
version output; explicit external-assembler selection flags and a sanitized
Clang driver probe that proves the exact assembler selected for every object
compile; a deterministic sanitized child
environment; response files; source, depfile-derived inputs, and before/after
input stability; and output digests. The final-link record additionally
preserves the unique ordered input list, binds each declared direct producer
record to the exact input bytes it produced, and hashes the ELF, dependency
file, map, and captured linker trace. The generic recorder does not interpret
that trace or require every ordered input to have a direct producer; the owning
product gate selects the required producer chains and proves contribution from
the link map, symbols, and disassembly. Failed post-command validation removes
the untrusted step outputs so a clean retry is possible.

Response-file support is deliberately one level deep. An argv-level `@file`
must be declared and is hashed, but any `@` byte inside it fails before the
target command runs because Clang/GNU nested-response tokenization is not yet
part of the generic evidence schema.

These JSON files are raw build-step evidence, not a release attestation or a
sandbox. Product policy must still authenticate the maintained source,
preparation envelope, selected profile, expected source/object inventory, and
qualification result. The runtime archive construction and ELF-to-BIN/HEX
objcopy steps are not currently recorded as actual steps; the final-link record
does hash the exact runtime archive consumed and `verify_firmware.py` continues
to check the derived binary. Use a new evidence directory for every invocation
and preserve a reviewed directory only when its owning product process calls
for it.

## 5. Normal development cycle

1. Edit the ZDS-oriented source in the writable checkout selected by
   `upstream/agon-mos`. Keep using the supported ZDS idioms, including scoped,
   anonymous, and macro-local labels.
2. If ZDS II is available, build and test there. This is useful cross-toolchain
   evidence but is not required before trying AgonDev.
3. Regenerate the prepared tree. The preparation script intentionally refuses
   to overwrite an existing destination. Preserve the last accepted tree while
   preparing the replacement:

   ```bash
   mv projects/mos-port/worktree projects/mos-port/worktree.backup
   .venv/bin/python scripts/prepare_mos_worktree.py
   ```

   If preparation fails, restore the backup and update the exact preparation
   rule that the maintained-source change invalidated. Never silently weaken a
   drift check.
4. Build with `make firmware-check`. Translation to GNU-as is automatic.
   If the frontend rejects a new ZDS form, first decide whether it is an
   ongoing source-language feature or a one-time port adjustment. Extend
   `zds2gas.py` only for the former, fail closed on ambiguous forms, and add
   positive, negative, object-level, diagnostic, and full-corpus coverage as
   applicable. Do not rewrite generated output or silently approximate ZDS
   behavior.
5. Run the focused checks relevant to the change, then emulator and hardware
   gates as appropriate. Emulator-coupled changes are subject to the human
   validation and commit-approval rule in `AGENTS.md`.
6. Once the new tree is accepted, the ignored `worktree.backup` is no longer
   needed. Confirm that exact path before removing it.

Before starting another refresh, either restore or relocate an existing
`worktree.backup`; the fixed backup name is intentionally never overwritten.

## 6. Where a change belongs

- Firmware behavior belongs in the maintained ZDS-oriented MOS source.
- A bounded, one-time portability adjustment belongs in
  `scripts/prepare_mos_worktree.py` with exact drift checks.
- An ongoing ZDS-language compatibility feature belongs in
  `projects/mos-port/tools/zds2gas.py` with semantic and diagnostic tests.
- Linker, runtime, and C compatibility contracts belong in their maintained
  areas under `projects/mos-port`.
- Generated `.asm`, object, map, and firmware files are never sources of a
  change.

A maintained product may pass `SOURCE_PROFILE=PATH` to declare additional C
translation units and corresponding runtime objects through `C_SOURCES_EXTRA`
and `C_OBJECT_RELATIVE_EXTRA`. It may append maintained ZDS assembly units and
their target-object paths through `ASM_SOURCES_EXTRA` and
`ASM_OBJECT_RELATIVE_EXTRA`; the two assembly lists must correspond exactly,
and an empty profile preserves the upstream source and link order unchanged.
Assembly composition validation accepts units only below `src/` or
`src_startup/` and rejects absolute, parent-traversing, non-canonical,
duplicate, missing, wrong-suffix, and symlink-escaping inputs before assembly.
The runtime closure derives providers from the target symbol tables of that
same exact, present, non-escaping linked object composition; merely placing or
textually exporting a symbol from another assembly file in the prepared source
tree grants it no provider authority. The runtime closure audit accepts a
metadata-only assembly provider only when its target definition comes from the
explicitly declared assembly-source/object suffix.
The profile may also supply product-specific preprocessor definitions through
`CPPFLAGS_EXTRA` and reviewed HELP-command additions. It may list
product-owned Python checkers in
`FIRMWARE_LINK_CHECKS`. The root `firmware-check` target invokes every listed
checker against the prepared source and final ELF through a fixed
`--source`, `--elf`, `--nm`, and `--objdump` interface. The profile is owned by
the product source repository. Generic build machinery consumes it but must
not duplicate or infer product policy.
`CPPFLAGS_EXTRA` is an explicit product-profile input; do not use it to hide a
generic compiler, header, or source-compatibility workaround.
When a definition is consumed by only one selected translation unit, set
`C_SOURCE_CPPFLAGS_RELATIVE` to that unit's relative `.c` path and put the
definition in `C_SOURCE_CPPFLAGS_EXTRA`. The generic build rejects an empty,
multiple, pattern-bearing, or unselected source name and applies those flags
only to that literal unit's object and inspection-assembly targets. In
particular, `%` is forbidden because GNU Make would reinterpret it as a target
pattern. Keep `CPPFLAGS_EXTRA` for definitions that genuinely affect every
selected C translation unit.

AgonDev correctly models the eZ80 ABI's 24-bit `unsigned int`. Assignment to a
32-bit destination does not widen an arithmetic expression that has already
been evaluated at 24-bit width. Treat inherited code that implicitly relies on
ZDS intermediate widths as a portability hazard, especially when it derives
hardware clocks, divisors, addresses, or transfer sizes. Put the corresponding
source-and-linked-image invariant in the product profile; emulator boot alone
is not evidence for a physical timing value.

Use the repository-root `firmware-check` for a supported product build. A
direct `projects/mos-port` sub-build deliberately provides only generic link
checks and does not satisfy profile-owned firmware invariants.

The accepted frontend contract is in
`docs/assembly-compatibility-strategy.md`; implementation details and the
supported syntax boundary are in `projects/mos-port/asm/README.md`.

## 7. Verification versus frozen research evidence

`make verify` exercises the current configured inputs without requiring a
particular checkout location or byte identity for a locally built Fab binary.
It still enforces the pinned AgonDev ABI/runtime contract and every current
firmware regression; portability is not permission to substitute an unaudited
toolchain or remove a required source fix.

`make baseline-check` additionally compares public source identities, toolchain
identity, source measurements, and stock firmware artifacts with
`evidence/baseline.json`. Schema 2 intentionally excludes a locally compiled
Fab executable because path/compiler differences need not change its public
source identity; the configured emulator profile still records and verifies
the exact executable it uses. Do not update the evidence file merely to silence
a mismatch; review every pin or measurement change deliberately.

## 8. About an AgonDev-native maintained fork

Maintaining GNU-as/AgonDev-native source directly is a possible future project
model, but this repository does not currently implement it. Editing
`projects/mos-port/worktree` or `projects/mos-port/generated` does not create
such a fork: both are ignored, reproducible state and their changes can be
discarded.

A native model would require a deliberately maintained source tree, new
provenance and synchronization rules, and a policy for merging later ZDS
upstream changes. Until that decision is made, maintain the ZDS-oriented source
and generate the AgonDev inputs.
