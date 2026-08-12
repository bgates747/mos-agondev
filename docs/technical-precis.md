# Technical Précis: Agon MOS to AgonDev

This précis records the compact technical basis for the feasibility decision.
The expanded rationale is in `feasibility-study.md`; implementation work is
owned by `TODO.md`.

## 1. Pinned basis

1. MOS: `upstream/agon-mos`, commit
   `5f67b1ca77eb7a77d3b37cc7b029db51f0d1548e`, clean branch
   `fix/vdp-oversize-discard`, description `v3.0.2-1-g5f67b1c`.
2. AgonDev: `../../agondev`, commit
   `b67ab2444a63267a42193f204889d466765d8dd2`, clean `master`, version
   `1.0`.
3. Compiler: Clang 15.0.7, Agon LLVM
   `c76386c0083e6a6236ff774275227e2389f85538`; assembler and linker are
   GNU Binutils 2.45.
4. Fab: `../../fab-agon-emulator`, commit
   `98bbb392b75b196171cc620b60839220e5ce53ed`, local tag description
   `1.2.2`; checkout was clean and one commit behind the observed remote.
5. Local VDP source reference: `../../agon-vdp`, commit
   `c7ac293d2aa81ddfa693390549bcd909069c8fc3`, tag `v2.16.0`.
6. Pinned stock artifacts: `mos_platform.bin`
   `d564243283972690933a4554296ad6202ca4ef54572279533a942960846bebae`,
   `mos_platform.map`
   `d69e60bbce61a7b4b3eef318ba395f11c4e1a5b585755755113992dc94edcb86`,
   and `vdp_platform.so`
   `cfd0aad2108e074af207f5bc6f1b73976097851405bc7c3f8949c7a165df2cb3`.

## 2. Current ZDS build contract

1. ZDS II eZ80Acclaim 5.3.5 is the documented compiler, assembler, IDE, and
   debugger; it emits `MOS.hex`, which is converted externally to `MOS.bin`:
   `upstream/agon-mos/README.md:39-53`.
2. The exact project input list is
   `upstream/agon-mos/MOS.zdsproj:5-40`.
3. Release C settings include `NDEBUG`, eZ80/eZ80F92 defines, speed
   optimization, promotion, and general printf generation:
   `upstream/agon-mos/MOS.zdsproj:179-195`.
4. ZDS links OMF695 and Intel32 outputs, creates map/xref data, includes custom
   startup and the C runtime, and defines ROM `0x000000-0x01FFFF` plus RAM
   `0x0BC000-0x0BFFFF`:
   `upstream/agon-mos/MOS.zdsproj:240-269`.
5. Target state is 18.432 MHz, ADL, SP `0x0C0000`, external RAM
   `0x040000-0x0BFFFF`, internal flash page 0, and internal RAM page `0xB7`:
   `upstream/agon-mos/eZ80F92_AGON_Flash.ztgt:3-57`.
6. The current stock Platform map records ROM 108,341/131,072 and RAM
   3,029/16,384 bytes:
   `../../fab-agon-emulator/firmware/mos_platform.map:115-121`.

## 3. ABI and C evidence

1. Published MOS ABI: reverse-order caller-cleaned stack arguments, each padded
   to a three-byte unit; `int` and pointers are 24-bit:
   `../../agon-docs/docs/mos/C-Functions.md:27-50`.
2. Return registers are `A` for eight-bit, `HLU` for 16/24-bit and pointers,
   and `E:HLU` for 32-bit values:
   `../../agon-docs/docs/mos/C-Functions.md:75-94`.
3. AgonDev supplies native 24-bit types:
   `toolchains/agondev/include/stdint.h:58-68`.
4. AgonDev generated output uses `_main` and three-byte stack operations:
   `../agondev-tests/hello_c/obj/main.s:1-16`.
5. The study's static assertions passed for 8-bit byte, 16-bit short, 24-bit
   int/pointer/size_t, and 32-bit long/float/double:
   `projects/toolchain-probe/src/type_model.c:5-12`.
6. Sixteen of 16 MOS C units compile. The build list and flags are recorded at
   `projects/mos-port/Makefile:8-44`.
7. The initial AgonDev C probe totaled 88,020 loadable bytes; the explicit
   `quickrand` return contract raises the current total to 88,054. Corresponding
   current ZDS C modules total 95,238 bytes. This is a C-only intermediate
   comparison, not a full-image prediction.
8. The initial syntax probe needed five experimental source-file changes. The
   accepted prepared worktree now applies 11 drift-checked file patches for
   linker arrays, portable include spelling, clock types, the 32-bit timestamp
   shift, explicit `quickrand`, and three reviewed long-branch selections.
9. `src_fatfs/ff.c` fails with AgonDev 1.0 register exhaustion at `-Oz` and
   `-O1`, and succeeds at `-Os`; the explicit override is
   `projects/mos-port/Makefile:46-48`.
10. ZDS peripheral names are C lvalues, whereas AgonDev's native header provides
    numeric register constants and `IO(addr)` using address space 3:
    `toolchains/agondev/include/ez80f92.h:8-15`. AgonDev's own
    timer demonstrates the intended access form:
    `../../agondev/src/lib/libtimer/timer.c:12-32`.
11. Upstream `quickrand()` relies on implicit ZDS inline-assembly return state:
    `upstream/agon-mos/main.c:127-131`. The prepared AgonDev branch now
    declares the `A` output and condition-code clobber explicitly, returns it as
    C, and is disassembly-checked for the required zero extension; the original
    ZDS branch is preserved.

## 4. Assembly evidence

1. Full assembly/include surface: 6,680 lines; active firmware surface is about
   6,382 after excluding the 298-line public `mos_api.inc`.
2. Supported in direct GNU-as probes: ADL assumptions, `JP.LIL`, `RET.L`,
   `RETI.L`, `RETN.LIL`, `RST.LIS`, `STMIX`, `MLT`, `PEA`, `LEA`, `EX`,
   `XDEF`, `XREF`, `EQU`, `SECTION`, `INCLUDE`, `END`, and ZDS conditional
   assembly.
3. Conversion inventory: 179 percent-prefixed numeric tokens, 76 `$F/$B`
   references, 64 `$$:` definitions, 26 binary-suffix literals, 21 `DL`/`DW24`
   uses, 19 scopes, 17 macro definitions/terminators, 15 segments, 14
   space-defines, and 14 wide pseudo-register copies.
4. Startup clears BSS and copies initialized data from ROM:
   `upstream/agon-mos/src_startup/cstartup.asm:12-89`.
5. Hardware startup consumes linker-generated chip-select/memory constants and
   sets SP:
   `upstream/agon-mos/src_startup/init_params_f92.asm:20-45` and
   `:101-156`.
6. Reset, vector, second-stage jump-table, and alignment contracts are explicit:
   `upstream/agon-mos/src_startup/vectors16.asm:60-99` and
   `:221-237`.
7. AgonDev's own dialect-conversion script covers common directives but not the
   MOS scope/linker problem:
   `../../agondev/scripts/convert_src_to_gnu-as.sh:5-27`.
8. Installed GNU `as` accepts repeated numeric labels with nearest `99f`/`99b`
   resolution, providing a direct semantic mapping for ZDS `$$:` and `$F`/`$B`.
9. Installed GNU `as` also accepts `.altmacro` `LOCAL` symbols and `\@` expansion
   identifiers; direct multiple-expansion probes produced independent local
   branches without exporting those labels in the object symbol table.
10. The selected initial approach is the strict ongoing compatibility frontend
    specified in `assembly-compatibility-strategy.md`. Maintained source keeps
    scoped/local-label idioms; generated GNU-as source owns any mangled names.

## 5. Linker and output evidence

1. AgonDev's default linker is a user-RAM application linker and is unsuitable
   for firmware:
   `toolchains/agondev/config/linker.conf:6-49`.
2. Its standard Makefile also links `-l agon` and runs `agondev-setname` on an
   application binary:
   `toolchains/agondev/config/makefile.inc:34-48` and `:72-81`.
3. The study custom linker defines flash `0x000000/0x020000`, RAM
   `0x0BC000/0x004000`, reset at zero, vectors at `0x100`, code at `0x220`,
   copied data, BSS, stack/heap symbols, and overflow assertions:
   `projects/toolchain-probe/ld/firmware.ld:1-65`.
4. Its verified ELF is ELF32 little-endian eZ80 ADL with entry zero; section
   addresses are `.reset=0`, `.vectors=0x100`, `.text=0x220`,
   `.data=0x0BC000`, and `.bss=0x0BC001`.
5. `objcopy -O binary` produced a 611-byte probe image with SHA-256
   `28528ac57eb024dfa2afad063db102cb11d115c87c2d3dfaf65bdb27a47647a9`.
6. The ZDS-generated linker contract is visible in the stock map: section order,
   copied DATA, startup symbols, chip-select values, and clock constant:
   `../../fab-agon-emulator/firmware/mos_platform.map:62-109`.

## 6. Runtime and capacity facts

1. ZDS extracts arithmetic, frame, memory/string, classification, conversion,
   sort, and printing modules from `chelp.lib`, `crt.lib`, `crtS.lib`, and
   `nokernel.lib`; the module inventory begins at
   `../../fab-agon-emulator/firmware/mos_platform.map:251`.
2. AgonDev `libagon.a` contains compatible Clang helper and libc symbols, but
   archive extraction and duplicate/application-facing symbols need a final-map
   audit.
3. AgonDev's application CRT0 is not a firmware startup; it creates a MOS
   application environment and exit path:
   `../../agondev/src/lib/libcrt0/crt0.src:29-76`.
4. AgonDev nanoprintf defaults large format specifiers off:
   `../../agondev/src/lib/libc/nanoprintf.h:101-117`.
5. MOS uses width-qualified 32-bit `%lu` at
   `upstream/agon-mos/src/mos.c:2159`, `:2295`, and `:2301`; formatter
   configuration and golden output tests are mandatory.
6. AgonDev's weak `_putchar` inserts CR before LF before invoking RST output:
   `../../agondev/src/lib/libc/putchar.src:6-22`. MOS emits explicit
   `\n\r` sequences, so the firmware formatter must use raw MOS `putch`
   semantics.
7. Stock Platform map headroom is 22,731 ROM bytes and 13,355 RAM bytes. The
   favorable 7,184-byte C-only delta could not be treated as final headroom
   before assembly and runtime were linked.

## 7. Fab emulator integration fact

1. Fab accepts explicit MOS and VDP paths:
   `../../fab-agon-emulator/src/parse_args.rs:29-39` and
   `:165-166`.
2. It first looks for a `MOS` ROM descriptor at offset `0x6B`, containing 25
   FatFS entry points:
   `../../fab-agon-emulator/agon-ez80-emulator/src/mos.rs:56-93`.
3. Without that descriptor, it searches for a same-stem `.map`; failure disables
   hostfs:
   `../../fab-agon-emulator/agon-ez80-emulator/src/agon_machine.rs:627-670`.
4. The fallback parser specifically expects the ZDS `EXTERNAL DEFINITIONS:`
   format:
   `../../fab-agon-emulator/agon-ez80-emulator/src/symbol_map.rs:14-48`.
5. The pinned stock Platform ROM lacks the descriptor, so its matching stock map
   must remain adjacent. A GNU-linked MOS needs the ROM descriptor, a compatible
   generated sidecar, or an emulator parser enhancement; a GNU map alone will
   disable hostfs. The candidate emits the descriptor and verifies all 25
   addresses. A raw SD image bypasses hostfs and its map dependency, but does
   not validate directory-backed hostfs.

## 8. Decision

The evidence supports continued implementation and qualification with
medium-high release risk. The full image now fits, boots with verified hostfs,
and passes bounded behavioral comparison; graphical, broad parity, upstream,
and physical-hardware gates remain. Until those pass, ZDS remains the reference
release build.

## 9. Implementation status — 2026-08-12

The feasibility gates through the first bootable image have now been crossed.
The candidate compiles all 16 C units, translates and assembles all 15 active
assembly roots, links an allow-listed runtime, and emits a fully resolved
102,059-byte binary plus ELF, GNU map, and Intel HEX. Fab's format-2 descriptor
at `0x6B` resolves all 25 FatFS hooks; the image boots with the stock Platform
VDP, mounts directory-backed hostfs, and matches the pinned ZDS build for
deterministic command/help parsing, process-local variables, RTC/credits,
nested hostfs traversal, and invalid-command handling.

The C compatibility layer now has a pinned nine-header/44-hardware-name
contract, type and register assertions, dependency-set checks, source rules,
and emitted-code checks. This upgrades the original build-feasibility
conclusion. The strict source-mapped frontend has also passed its lexical,
golden, object, relocation, disassembly, diagnostic, structure, provenance, and
full-corpus gates without globalizing maintained-source locals. A target
contract covers every formatter spelling and a bounded read-only wrapper/ABI
set; its source-wide audit identified three pinned AgonDev libmos defects and a
Fab large-file hostfs limitation, recorded in `upstream-findings.md`. The
linked-byte VDP gate covers the blocking startup poll and every oversized
one-byte packet length. The graphical human gate, broad emulator/API parity,
upstream coordination, and physical hardware testing remain in the
authoritative TODO.
