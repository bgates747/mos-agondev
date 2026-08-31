# Firmware runtime candidate

This directory turns the `PORT-104` runtime policy into a linkable, restricted
archive. The firmware must link `build/libmos_runtime.a`, not the complete
AgonDev `libagon.a`. The generated archive contains only the members named in
`runtime_policy.json`, so application CRT, MOS-client wrappers, and unrelated
library code are unavailable to the firmware linker.

Run the complete local qualification from the repository root with:

```bash
make -C projects/mos-port/runtime clean verify
```

The build uses an explicit 16-object MOS C contract. The parent firmware build
links this archive into the complete candidate, which has passed the initial
headless boot and shell-parity gates.

## 1. Runtime boundary

1. `audit_runtime.py` computes the transitive archive closure from actual ELF
   symbols and relocations. Its input is the 16-object `c_objects` contract in
   `runtime_policy.json`, so translated assembly below `obj/asm` cannot alter
   the runtime closure. It classifies providers as existing C objects,
   maintained MOS assembly `XDEF`s, linker symbols, local runtime objects, or
   AgonDev archive members. The parent build passes the same configured
   maintained-source tree used for translation as `ASSEMBLY_SOURCE`; the audit
   must not silently scan a different default prepared tree.
2. `runtime_policy.json` currently allows 43 compiler-helper members and 22
   freestanding libc members from the pinned AgonDev archive. The generated
   archive adds two local objects, for 67 explicit members total.
3. `build_runtime_archive.py` checks the source `libagon.a` SHA-256, extracts
   only those named members, builds a fresh restricted archive, and verifies
   its exact ordered member list.
4. The relocatable link probe combines all 16 C objects with that restricted
   archive. Every remaining relocated undefined symbol is supplied by MOS
   assembly or the production linker script. Three unreferenced undefined symbols
   are assembler metadata artifacts and are named explicitly in the policy.
5. The current restricted runtime contributes 5,719 bytes of text and 54 bytes
   of read-only data, for 5,773 loadable bytes and no data or BSS. Combined C
   plus runtime sections are 83,824 text, 9,268 read-only data, 735 data, and
   1,726 BSS bytes.

The explicitly forbidden archive members include `crt0.o`, argument and stdio
state setup, the monolithic `nanoprintf.o`, `fputc.o`, and the MOS-client
`putch.o`/`putchar.o` variants. The audit also proves that `_putch`, `_printf`,
and `_sprintf` are shadowed by their required firmware providers instead of
being selected from `libagon.a`.

## 2. Formatter binding

`formatter/firmware_printf.c` builds a private nanoprintf implementation and
exports only `printf` and `sprintf`. Its callback invokes the maintained MOS
assembly `putch` routine directly; it does not call RST, translate newlines, or
depend on stdio streams.

The formatter enables field width and precision and disables float, `hh`/`h`,
`ll`/`j`/`z`/`t`, binary, `%n`, and alternate-form support. In nanoprintf,
`NANOPRINTF_USE_LARGE_FORMAT_SPECIFIERS=0` does **not** disable `%ld`/`%lu`.
On this target, `unsigned long` is wider than `uintptr_t`, so nanoprintf selects
the 32-bit long accumulator. Target static assertions preserve that assumption.

`scan_formats.py` currently finds 174 literal `printf`/`sprintf` calls and 182
conversion specifiers. They use only `%`, `c`, `d`, `s`, `u`, `x`, and `X`;
the only length-qualified form is the three `%*lu` directory-size uses. The
host golden program covers target-width 24-bit integer boundaries, 32-bit long
boundaries, dynamic width, dynamic precision, padding, uppercase hexadecimal,
and raw `\n\r` byte order. It has an explicit case for every distinct formatter
spelling found in maintained MOS. `scan_formats.py` compares the inventoried
spellings with unique `GOLDEN_PATTERN` markers, preventing a new or removed
format from silently drifting away from the golden corpus. The separate target
contract links this exact formatter source and repeats all 16 spellings at eZ80
boundary values against both candidate and ZDS firmware. Broader exported ABI
coverage remains MOS parity work.

The implementation vendors the AgonDev-modified nanoprintf 0.5.5 header at pinned
SHA-256 `30ac848df4b8713d42194b87aeb23f10e86f39002f46441f7ecf89512106979d`.
The hash is checked during the runtime audit.

## 3. Split 48-bit helpers

FatFS's `(len + 12) / 13` optimization causes Clang to emit `__i48mulu` and
`__i48shru`. AgonDev supplies both in one monolithic `i48stubs.o` alongside all
other 48-bit operations. Selecting that member would retain its complete
64-bit helper dependency family.

`helpers/i48_required.asm` splits out only those two existing stubs, leaving
their required `__llmulu` and `__llshru` providers in the allow-list and
forbidding `i48stubs.o`. `verify_i48_helpers.py` extracts the pinned archive
member and compares each local routine's assembled bytes with the reference on
every verification run.

## 4. Files

- `runtime_policy.json` is the machine-readable provider and format contract.
- `audit_runtime.py` performs closure, provenance, member, size, and link-probe
  checks.
- `build_runtime_archive.py` creates the physically restricted archive.
- `scan_formats.py` inventories maintained MOS format strings.
- `formatter/` contains the firmware binding and host golden program.
- `helpers/` contains the two split compiler stubs.
- `tests/` contains host-side regression tests for the audit tools.
