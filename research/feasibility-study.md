# Feasibility Study: Building Agon MOS with AgonDev

> Historical research snapshot. Use `STARTHERE.md` for current setup,
> `docs/README.md` for current technical contracts, and `TODO.md` for active
> work.

> Implementation update (2026-08-12): the recommended path has produced a
> fully resolved 102,059-byte candidate that boots, mounts Fab directory-backed
> hostfs through a format-2 ROM descriptor, and passes a limited shell-output
> comparison with the pinned ZDS image. The findings below preserve the
> original study rationale; current remaining work is tracked only in TODO.md.

Status: implementation feasibility established; release qualification pending
Assessment: **feasible, with remaining parity and hardware gates**
Delivery risk: **medium-high for release use** until graphical, broad parity,
and physical-hardware gates pass

## 1. Executive determination

AgonDev can plausibly replace the Zilog Developer Studio II toolchain for Agon
MOS. The study found no eZ80 instruction-set or C ABI incompatibility. AgonDev
1.0 successfully compiled all 16 MOS C translation units after five small
source-level portability changes, compatibility headers, and one per-file
optimization workaround. A separate probe successfully linked an ADL firmware
ELF with reset code at `0x000000`, vectors at `0x000100`, code at `0x000220`,
initialized data in MOS RAM, and a flat binary output.

This was not a Makefile-only conversion. The original study identified four
material bodies of work:

1. Port 6,680 lines of ZDS-dialect assembly and includes to the GNU assembler
   dialect accepted by AgonDev.
2. Reconstruct ZDS's generated firmware linker contract explicitly, including
   section locations, copied data, heap/stack symbols, and hardware-init
   constants.
3. Select and validate a firmware-safe C runtime, particularly formatted
   output and compiler helper routines.
4. Prove behavioral parity in Fab Agon Emulator and then on physical hardware.

Implementation has closed the assembly, linker, runtime, size, boot, and
initial headless-comparison gates. The decision is now a go for continued port
qualification, with graphical, broader behavioral, upstream, and hardware
gates before claiming that AgonDev can replace ZDS for releases. The
authoritative work inventory is `TODO.md`; the phases below preserve the
original sequencing and decision criteria rather than forming a second task
list.

## 2. Scope and method

The study examined the local source, toolchain, documentation, ZDS build map,
and emulator implementation. Upstream repositories were treated as read-only.
Experimental portability changes and generated objects live only in this
study's `projects/` area.

The evidence comprises:

1. Static inspection of `agon-mos`, its ZDS project, target description,
   startup code, assembly sources, and published ABI documentation.
2. Direct compiler, assembler, linker, object inspection, and size probes using
   the locally installed AgonDev toolchain.
3. Compilation of every C source listed by the ZDS project.
4. Comparison with the current stock Platform ZDS map and binary carried by Fab
   Agon Emulator.
5. Inspection of Fab's MOS-loading, map-parsing, and host-filesystem hooks.

At the original evidence cutoff no complete AgonDev-built MOS image existed,
so the study itself did not claim boot or behavioral parity. The implementation
update above and current development log supersede that historical limitation.

## 3. Reproducibility baseline

### 3.1 Source and tool pins

| Component | Local path | Pinned state |
|---|---|---|
| MOS source | `upstream/agon-mos` | `5f67b1ca77eb7a77d3b37cc7b029db51f0d1548e`, branch `fix/vdp-oversize-discard`, clean |
| AgonDev source | `agondev` | `b67ab2444a63267a42193f204889d466765d8dd2`, branch `master`, clean |
| Fab emulator source | `fab-agon-emulator` | `98bbb392b75b196171cc620b60839220e5ce53ed`, tag description `1.2.2`, clean but one commit behind recorded `origin/main` |
| VDP source reference | `agon-vdp` | `c7ac293d2aa81ddfa693390549bcd909069c8fc3`, tag `v2.16.0`, clean |

The MOS pin is one commit after tag `v3.0.2`; relative to local `main`, it changes
`src/vdp_protocol.asm` and adds the oversized-packet regression test. The VDP
source pin is a reference checkout; the stock emulator shared object is pinned
separately by hash and is not asserted to have been built from that checkout.

AgonDev reports version `1.0`. Its installed components are:

- Clang 15.0.7, Agon LLVM commit
  `c76386c0083e6a6236ff774275227e2389f85538`, target
  `ez80-none-unknown-elf`.
- GNU assembler 2.45 for `ez80-none-elf`.
- GNU linker 2.45 for `ez80-none-elf`.

Installed-tool hashes used during the study:

| Artifact | SHA-256 |
|---|---|
| `ez80-none-elf-clang` | `34670dda66966bc83b59bafe97bbe84fd7ca20ad15728eb3f3753097d22dc51d` |
| `ez80-none-elf-as` | `00dec630d1c386521887e6af0bb1b2045f66ae6f181f84491269f020a0342bdb` |
| `ez80-none-elf-ld` | `2f4321d67956d8389bc28661b8684f8e054ee3b4e9eb890245f6c9afa33434cf` |
| `libagon.a` | `5de7878342ab6780593fbf8d54d8005960e2471bd0e34c0e307fbcfe42fef28a` |

### 3.2 Stock emulator artifact pins

The local emulator instance should initially use these unchanged stock
artifacts:

| Artifact | Size | SHA-256 |
|---|---:|---|
| `mos_platform.bin` | 108,490 bytes | `d564243283972690933a4554296ad6202ca4ef54572279533a942960846bebae` |
| `mos_platform.map` | 167,185 bytes | `d69e60bbce61a7b4b3eef318ba395f11c4e1a5b585755755113992dc94edcb86` |
| `vdp_platform.so` | 10,279,496 bytes | `cfd0aad2108e074af207f5bc6f1b73976097851405bc7c3f8949c7a165df2cb3` |
| `fab-agon-emulator` | local executable | `a67e9fa52cdc55816e1c3d4224defa2c8b140c7ee4f48178695b54f6743fe5dc` |

The sibling stock map is operationally significant, not merely diagnostic; see
Finding 7.

## 4. Stable findings

### Finding 1: the CPU model and C ABI are compatible

AgonDev accepted compile-time assertions for the data model MOS expects:

| C type | AgonDev size |
|---|---:|
| `char` | 1 byte |
| `short` | 2 bytes |
| `int` | 3 bytes |
| `long` | 4 bytes |
| pointer | 3 bytes |
| `size_t` | 3 bytes |
| `float` | 4 bytes |
| `double` | 4 bytes |

AgonDev also exposes `int24_t` and `uint24_t`. Generated assembly uses leading
underscores for C symbols and the expected three-byte ADL stack convention.
This agrees with the published MOS/Zilog convention: caller-cleaned arguments
are pushed in reverse order and padded to three-byte slots, `int` and pointers
are 24-bit, and an eight-bit return value is delivered in `A`.

This removes the largest possible architectural blocker. It does not by itself
prove that every ZDS extension or undefined C construct has identical semantics.

### Finding 2: all MOS C translation units compile with a small portability shim

The study compiled all 16 C sources listed in the ZDS project. The initial
object set contained 88,020 loadable C bytes (`.text + .rodata + .data`); the
hardened `quickrand` contract brings the maintained probe to 88,054, with
1,726 bytes of C BSS. The corresponding currently linked ZDS C modules account
for 95,238 loadable bytes (`CODE + STRSECT + TEXT + DATA`). The current
AgonDev result is 7,184 bytes, or about 7.5%, smaller at this intermediate
comparison point.

That comparison is encouraging but not a final ROM forecast. It excludes the
ported MOS assembly and the AgonDev runtime, and it compares relocatable
AgonDev sections with modules selected into a completed ZDS link.

The original probe needed five source-file changes:

1. `main.c`: give linker-provided `_heapbot` an object type rather than declaring
   an array of `void`.
2. `src/defines.h`: give six linker-provided region symbols an object type for
   the same reason.
3. `src/clock.h`: include the type definitions it uses instead of relying on
   include order.
4. `src/mos.c`: give linker-provided `sysvars` an object type rather than an
   array of `void`.
5. `src_fatfs/diskio.c`: cast the year difference to `DWORD` before shifting it
   by 25, avoiding a 24-bit intermediate.

The implementation subsequently hardened this into 11 drift-checked prepared
paths. Portable include spellings select AgonDev's official headers; a narrow
local facade provides only the Zilog aliases and peripheral lvalues agon-mos
uses. The contract pins nine transitive official header hashes, audits 44
hardware names, asserts type/register values, checks emitted I/O instructions,
and preserves the original ZDS branch of `quickrand` while giving AgonDev an
explicit register result and return.

One compiler-specific workaround is required. AgonDev 1.0 exhausts registers
while compiling `src_fatfs/ff.c` at `-Oz` and at `-O1`; compiling that
translation unit at `-Os` succeeds. The per-file exception is recorded in
`projects/mos-port/Makefile` and should remain explicit and regression-tested.

Return-type diagnostics are now errors. The C compatibility verifier checks
that AgonDev emits `ld a,r` followed by the expected zero extension into HLU and
`ret`, and independently proves the FatFS timestamp expression uses its 32-bit
shift helper.

### Finding 3: the eZ80 instruction set is supported; the assembly dialect needs a bounded port

The MOS assembly surface is 6,680 source lines across `src/*.{asm,inc}` and
`src_startup/*.asm`. Of those, 298 lines are the exported `mos_api.inc`, which
is listed in the IDE project but is not included by the firmware assembly
inputs. The active firmware surface is therefore approximately 6,382 lines;
the public include still matters for a complete toolchain transition.

Direct no-output assembler probes show that AgonDev's GNU assembler accepts the
important CPU syntax, including ADL assumptions, `JP.LIL`, `RET.L`, `RETI.L`,
`RETN.LIL`, `RST.LIS`, `STMIX`, `MLT`, `PEA`, `LEA`, and `EX`. It also accepts
several ZDS-compatible directives and spellings: `XDEF`, `XREF`, `EQU`,
`SECTION`, `INCLUDE`, `END`, `IF/ELSE/ENDIF`, and hexadecimal `0ffh` suffixes.

The mechanically identifiable incompatibilities are:

| ZDS construct | Occurrences in full assembly/include surface | AgonDev/GNU replacement |
|---|---:|---|
| percent-prefixed numeric tokens such as `%FF` | 179 | `0xFF`, `0FFh`, or the intended expression |
| `$F`/`$B` local-label references | 76 | GNU numeric labels or unique `.L` labels |
| `$$:` local-label definitions | 64 | GNU numeric labels or unique `.L` labels |
| binary suffix literals such as `00000001b` | 26 | `0b00000001` |
| `DL` (32-bit) | included in 21 `DL`/`DW24` uses | `d32` |
| `DW24` (24-bit) | included in 21 `DL`/`DW24` uses | `d24` |
| `SCOPE` | 19 | remove after making local labels unique |
| `MACRO` definitions and ZDS terminators | 17 | `.macro` / `.endm` |
| `SEGMENT` | 15 | `.section` or accepted `SECTION` form |
| `DEFINE ... SPACE` | 14 | explicit section plus linker placement |
| wide pseudo-register copies such as `LD DE,HL` | 14 | semantically equivalent push/pop or instruction sequence |

The macro library additionally uses token concatenation and named local labels.
Those constructs need listing-level inspection after conversion. The public
`mos_api.inc` uses ZDS `.STRUCT`, `.TAG`, and `.ENDSTRUCT`; because it is not an
active firmware input, it can be ported after the firmware assembler closes.

This is a moderate conversion, not a new assembler backend. It should be done
in small source groups while preserving instruction semantics. In particular,
dialect conversion must not be combined casually with changes to ADL
multibyte-memory widths.

The selected initial approach is a strict ongoing Python compatibility frontend,
not manual globalization of ZDS local labels. Anonymous labels map naturally to
GNU numeric forward/backward labels; named locals remain scoped in maintained
source and receive generated `.L` identities; macro locals use GNU `LOCAL` or
`\@`. Alternatives, the distinction between one-time migration tools and an
ongoing supported source language, and the acceptance criteria are specified in
`docs/assembly-compatibility-strategy.md`.

### Finding 4: a custom firmware linker script works and is mandatory

AgonDev's stock linker script is for applications loaded into user RAM. It has
one `USERRAM` region, an application entry point, application CRT symbols, and
no flash load image. Its stock Makefile also applies `agondev-setname`, which
patches a MOS application header. Neither behavior is appropriate for MOS
firmware.

The study's custom-linker probe successfully produced:

- an ELF32 little-endian eZ80 executable with ADL flag `0x84` and entry point
  `0x000000`;
- `.reset` at `0x000000`, size 9;
- `.vectors` at `0x000100`, size `0x120`;
- `.text` at `0x000220`;
- `.data` at `0x0BC000` with a flash load address;
- `.bss` as `NOBITS` at `0x0BC001`;
- a 611-byte flat binary whose SHA-256 is
  `28528ac57eb024dfa2afad063db102cb11d115c87c2d3dfaf65bdb27a47647a9`.

The probe proves that `ez80-none-elf-ld` and `objcopy -O binary` can express the
basic firmware shape. A production script must additionally reproduce the full
ZDS contract:

1. Flash `0x000000-0x01FFFF` and MOS RAM `0x0BC000-0x0BFFFF`.
2. Reset at zero, interrupt vectors aligned at `0x100`, and startup/code after
   the vector block.
3. Read-only code and strings in flash.
4. Initialized data with RAM VMA and flash LMA, plus zero-initialized BSS.
5. The RAM second-stage interrupt jump table.
6. Exact startup symbols for data/BSS/code copy, heap, stack, and clock.
7. Chip-select, flash, and internal-RAM constants presently generated from the
   ZDS target file.
8. Link-time assertions for reset/vector overlap, ROM overflow, RAM overflow,
   and any descriptor reservation adopted for Fab.

The intended outputs should be an ELF for inspection/debugging, a GNU map, a
flat `MOS.bin`, an optional Intel HEX file, disassembly/size reports, and a
manifest recording source and tool hashes. OMF695 output is not needed for the
emulator or normal firmware flashing.

### Finding 5: startup behavior is explicit enough to reproduce

The MOS startup sources consume the linker contract directly. They clear BSS,
copy initialized data from flash to RAM, optionally copy code, initialize chip
selects and internal memory mapping, set the stack to `0x0C0000`, initialize
interrupt vectors, and call `_main` in ADL mode.

The current ZDS link orders `.RESET`, `.IVECTS`, `.STARTUP`, `CODE`, and `DATA`,
copies the DATA load image to ROM, and generates all of the startup and target
symbols. This behavior is visible in the stock map, so it can be translated
into explicit GNU linker expressions rather than reverse engineered from the
binary.

Symbol spelling needs an explicit audit. AgonDev prefixes C symbols with an
underscore, while assembly and linker-defined names may already begin with
underscores. The production link should verify each contract with `nm` rather
than copying the triple-underscore conventions from AgonDev's application CRT.

### Finding 6: runtime selection and formatted output are the largest code/behavior uncertainty

The ZDS image links selected modules from `chelp.lib`, `crt.lib`, `crtS.lib`,
`nokernel.lib`, and a device-init dummy object. The map shows integer and long
arithmetic helpers, indirect-call/frame helpers, memory/string routines,
character classification, number conversion, sorting, and ZDS's specialized
formatted-output helpers.

AgonDev's `libagon.a` contains the relevant Clang arithmetic helpers and much of
the required libc surface. It is therefore a plausible provider, but it must be
audited by the final link map. The stock AgonDev CRT0 must not be used: it builds
a MOS-loaded application header, handles application arguments and exit, and
returns to an already-running MOS.

Formatted output needed an intentional decision. The ZDS project enables
`genprintf`; the ZDS map contains specialized print support rather than one
ordinary `_printf`. MOS uses width-qualified 32-bit `%lu` formatting in its
directory displays. On this eZ80 target nanoprintf selects a 32-bit long
accumulator even with its large-specifier option disabled, but a stock
monolithic `_printf` link is still not sufficient evidence. The implemented
port uses a firmware-local formatter and compares every maintained format
spelling at host and target boundaries.

The output sink must also be deliberate. AgonDev's weak application
`_putchar` inserts carriage return before line feed and then uses a MOS RST
path. MOS already emits explicit `\n\r` sequences and needs raw byte output;
using the weak shim would change its byte stream. Firmware should bind the
formatter directly to MOS's raw UART `putch` behavior and avoid depending on an
application shim.

### Finding 7: Fab requires either a ROM descriptor or a ZDS-format sibling map for hostfs

Fab loads the selected MOS binary and first looks at ROM offset `0x6B` for a
toolchain-neutral descriptor beginning with `MOS`. The descriptor contains 25
three-byte FatFS entry-point addresses. If it is absent, Fab changes the binary
suffix to `.map`, parses a ZDS `EXTERNAL DEFINITIONS:` table, and extracts those
same symbol addresses.

The pinned stock Platform ROM does not contain the descriptor signature. It
therefore depends on `mos_platform.map` being adjacent to
`mos_platform.bin`. A GNU linker map does not have the ZDS format expected by
Fab's fallback parser. If neither mechanism succeeds, Fab disables its
host-filesystem integration. MOS may still boot, which makes this failure easy
to mistake for a filesystem bug in the port.

The preferred toolchain-neutral solution is to reserve and emit Fab's ROM
descriptor table in the AgonDev image, with a linker assertion keeping reset
code out of that range. An alternative is a generated ZDS-compatible symbol
sidecar or an emulator enhancement that reads ELF/GNU maps, but either approach
adds coupling outside the firmware. A raw SD image bypasses hostfs and therefore
also avoids the map dependency, but it does not test directory-backed hostfs.
The implemented candidate emits the descriptor and verifies all 25 linked FatFS
addresses. A directory-backed stock emulator instance still needs the matching
stock map alongside the descriptor-less stock binary.

### Finding 8: current size evidence is favorable but leaves runtime pressure

The pinned Platform ZDS map reports:

| Region | Capacity | Used | Remaining |
|---|---:|---:|---:|
| ROM | 131,072 | 108,341 | 22,731 |
| MOS RAM | 16,384 | 3,029 | 13,355 |

The binary file is 108,490 bytes because file extent also reflects fixed
placement gaps. The ROM map's `Used` figure is the appropriate measure for
section contribution; both map use and final binary extent should be gated in
the new build.

The 7,184-byte reduction seen in the C-only comparison is helpful, but it is not
bankable headroom until the assembly and runtime are linked. The largest risks
to ROM are a generic printf implementation, duplicated application/runtime
shims, and loss of ZDS code-generation specialization. RAM has substantially
more apparent margin, but final data/BSS, interrupt jump-table, heap bottom, and
the reserved stack allowance must all be checked from the completed map.

### Finding 9: release equivalence requires emulator and hardware validation

Fab accepts explicit `--mos`, `--vdp`, and `--sdcard` paths, making an isolated
local instance suitable for repeated tests without modifying the upstream
emulator checkout. It emulates the 18.432 MHz eZ80, UART-to-VDP link, SD card,
interrupts, timers, GPIO, and relevant peripherals closely enough for the first
gate.

Upstream MOS documentation explicitly warns that Fab is not 100% accurate and
recommends emulator testing before hardware. A successful Fab boot cannot
close timing-sensitive UART/SPI/I2C, flash, interrupt, warm-boot, or recovery
risks. Hardware testing and a known-good recovery path remain required.

The branch's three original oversized-VDP-packet Python tests are a
source-aware model. The implementation now also executes the corresponding
path from the final linked candidate bytes for every one-byte oversized length,
using the pre-fix ZDS image as a pinned negative control. This closes the
linked-code regression but is not an end-to-end serial injection or broad VDP
protocol/timing test.

## 5. Risk assessment

| Risk | Likelihood before implementation | Impact | Containment |
|---|---|---|---|
| Incorrect reset/vector/data-copy layout | Medium | Critical | Explicit linker script, assertions, ELF/map inspection, byte-level reset/vector tests |
| Assembly dialect conversion changes semantics | Medium | High | Mechanical conversion in small groups, listings/disassembly, focused unit probes |
| Runtime helper or symbol mismatch | Medium | High | Allow-list unresolved/extracted archive members, `nm`/map audit, ABI tests |
| Formatter lacks MOS format behavior | High without intervention | Medium-high | Required-feature configuration and golden output tests |
| Final image exceeds 128 KiB | Medium | Critical | Link assertion and size trend at every phase |
| Fab hostfs silently disables itself | High without descriptor/map action | Medium | ROM descriptor or compatible sidecar; explicit startup check |
| Emulator pass masks hardware timing defects | Medium | High | Physical-device test matrix and recovery image |
| AgonDev 1.0 compiler regression | Medium | Medium-high | Pin hashes, retain `ff.c -Os`, add compiler/output regression tests |

## 6. Recommended implementation phases

### Phase 0: freeze reproducible references

Retain the pinned source/tool/artifact manifest, the stock Platform binary and
map, and a ZDS-produced reference image/map for the exact MOS source commit if
one can be produced. Record observable boot, command, filesystem, RTC, and VDP
behavior before replacing components.

Decision criterion: the baseline is repeatable without writing into any
upstream checkout.

### Phase 1: make the C portability layer production-quality

Convert the initial experimental source changes into reviewed patches, keep the
compatibility layer narrow, replace the `quickrand` return-register idiom, and
turn relevant warnings back into errors. Preserve the explicit `ff.c -Os`
workaround with a documented compiler-version condition.

Decision criterion: 16 of 16 C units compile reproducibly with no unexplained
warnings, and data-model/ABI/object-size tests pass.

### Phase 2: port assembly by subsystem

Port shared includes/macros first, then startup/vectors/globals, low-level
drivers, protocol/interrupt code, and finally the large MOS API wrapper. Keep
public `mos_api.inc` as a separate compatibility deliverable after the active
firmware input set assembles.

Decision criterion: every assembly input produces an ELF object, expected
symbols/sections are present, and targeted instruction/macro probes match the
ZDS intent.

### Phase 3: close linker and runtime

Expand the proven firmware linker script to the full ZDS contract, retain MOS's
own startup, select only required AgonDev library members, configure formatted
output, and emit the ROM descriptor or other explicit Fab hostfs solution.

Decision criterion: the full image links with no unexplained symbols, passes
layout assertions, fits both memory windows, and survives independent ELF/map/
binary consistency checks.

### Phase 4: emulator parity

Run the candidate with the pinned stock VDP and isolated SD card. Exercise cold
and warm boot, VDP handshake and packets, keyboard, command parsing, memory and
system variables, RTC, SD/FatFS, directory formatting, UART, and available
interrupt/peripheral paths. Compare results with the reference image.

Decision criterion: repeated clean boots and the agreed emulator regression
suite pass, including verified hostfs mode rather than silently disabled
integration.

### Phase 5: hardware qualification

Test on representative Agon hardware with a separately retained recovery path.
Include flash/update behavior, cold/warm reset, SD media, UART flow control,
VDP startup at full rate, timers/interrupts, RTC, SPI, and I2C.

Decision criterion: the agreed hardware matrix passes and any output/timing
differences from ZDS are understood and accepted.

### Phase 6: release and upstream-readiness

Document the pinned toolchain, deterministic build, artifact manifest, map/size
reports, emulator launch path, flashing/recovery procedure, and known compiler
workarounds. Decide whether compatibility headers remain private to the build or
become an upstream-supported AgonDev MOS layer.

Decision criterion: a clean checkout can reproduce the qualified image and all
release evidence without ZDS or Hex2Bin.

## 7. Final recommendation

Proceed with the port under the phased gates above. The successful 16-of-16 C
compile, favorable C size comparison, compatible ABI, supported eZ80 opcode
set, and working custom-linker probe made outright infeasibility unlikely. The
first four implementation risks named here—assembly, linker, formatter, and ROM
budget—have since produced a verified 102,059-byte bootable image; current
status and remaining parity gates are summarized near the start of this
document. Hardware validation remains on the critical path.

The study should be considered upgraded from “conditionally feasible” to
“feasible for release use” only after Phase 5 passes. Until then, ZDS remains
the reference release toolchain even if AgonDev images boot in Fab.
