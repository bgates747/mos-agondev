# Upstream findings from the MOS AgonDev port

This document is a durable, shareable report of defects or externally owned
limitations found while porting `agon-mos` to AgonDev. It records evidence; the
project's only actionable work list remains `TODO.md`.

Unless a finding gives its own newer pins, the original findings were
reproduced against:

- AgonDev commit `b67ab2444a63267a42193f204889d466765d8dd2`;
- Fab Agon Emulator commit `fbb7d7ca887a06966ca8a62ed22272409a5ab640`;
- maintained generic `agon-mos` source containing the reviewed oversized-packet
  correction on top of official v3.0.2.

No upstream checkout was modified. The executable audit, target MOSlet, local
workarounds, and fuller coverage boundary are under `projects/contract-probe/`.

## AgonDev libmos: three confirmed wrapper defects

AgonDev Clang gives every C argument up to 24 bits a three-byte stack slot. A
32-bit `long` occupies two three-byte words. After a conventional wrapper
prologue (`push ix; ld ix,0; add ix,sp`), argument starts are therefore IX+6,
IX+9, IX+12, and so on.

`projects/contract-probe/audit/abi_slot_probe.c` compiles representative mixed
width calls with the pinned compiler. `audit_wrappers.py` disassembles that
object, inventories all 123 pinned libmos wrapper sources, checks the installed
`libagon.a`, and verifies the corrected local wrappers. Run:

```bash
make -C projects/contract-probe audit
make contract-check
```

The second command runs an isolated AgonDev MOSlet against both the
AgonDev-built MOS and pinned ZDS MOS. Read assertions use fixed inputs; write
assertions perform a two-cold-boot transaction in a disposable hostfs and prove
exact cleanup. The complete repository gate is `make verify`.

### AGONDEV-LIBMOS-001 — `mos_getError` uses packed offsets

Affected source: `src/lib/libmos/mos_getError.src`, lines 9–11 at the pinned
commit.

Current code loads the one-byte error at IX+6, then assumes that the following
pointer starts immediately at IX+7 and the length at IX+10:

```asm
ld e,(ix+6)
ld hl,(ix+7)
ld bc,(ix+10)
```

The compiler emits three-byte slots, so IX+7 and IX+10 point inside preceding
arguments. The correct sequence is:

```asm
ld e,(ix+6)
ld hl,(ix+9)
ld bc,(ix+12)
```

The faulty installed archive wrapper left the caller's output buffer unchanged
in the target probe. The corrected project-local
`src/mos_getError_fixed.asm` successfully returns `Could not find file` for
`FR_NO_FILE` under both firmware images. The verifier checks that the local
object is selected, disassembles the three corrected offsets, and executes the
call.

### AGONDEV-LIBMOS-002 — `ffs_setlabel` overwrites its valid argument via IX

Affected source: `src/lib/libmos/ffs_setlabel.src`, lines 6–12.

The wrapper's stack-exchange sequence already places its sole pointer argument
in HL:

```asm
pop de
ex (sp),hl
push de
```

It then executes `ld hl,(ix+6)` without establishing an IX frame. That discards
the valid argument and reads through whatever IX value the caller happened to
have. The safe fix is simply to remove the redundant IX load and issue the RST
with the existing HL value.

`src/ffs_setlabel_fixed.asm` is assembled and disassembled by the audit. It is
deliberately not executed because mutating a volume label is outside the
directory-hostfs contract; ordinary file and directory writes are executed in
a disposable fixture.

### AGONDEV-LIBMOS-003 — `mos_flseek_p` points at the upper long word

Affected source: `src/lib/libmos/mos_flseek_p.src`, lines 6–15.

The wrapper correctly obtains the first `uint8_t` argument with the
stack-exchange idiom. At that point, the following `uint32_t` begins at SP+6:
the return address occupies three bytes, the first argument occupies another
three, and the 32-bit value occupies two three-byte words. Current code uses
SP+9, which points to the value's upper word:

```asm
ld hl,9
add hl,sp
```

The correction is `ld hl,6`. The target probe links
`src/mos_flseek_p_fixed.asm`, opens a fixed read-only file, seeks to offset 3,
and reads the expected byte under both firmware images. The audit separately
checks the compiler call slots and both archive and corrected disassembly.

### Audit scope

The source-wide structural audit found exactly these three defect shapes:

- 123 wrapper sources;
- 48 conventional IX-framed wrappers;
- 28 single-argument stack-exchange wrappers;
- 10 wrappers that delegate to a MOS-resident C function;
- 88 wrappers containing a direct `RST.LIL 08h`;
- 126 `(ix+N)` operands.

It found no other non-three-byte framed argument offsets, no other unframed IX
reader, and no other explicit SP-derived argument pointer. This rules out more
instances of these precise mechanical errors at the pinned commit. It is not a
semantic proof of all wrappers, callbacks, return widening, or hardware paths.

## Fab directory-hostfs: file size is truncated to 24 bits

### FAB-HOSTFS-001 — `FIL.obj.objsize` uses `_poke24`

Affected source: `agon-ez80-emulator/src/agon_machine.rs`, line 1429 at the
pinned Fab commit.

When directory-backed hostfs opens a file, Fab writes its length into FatFS's
32-bit `FIL.obj.objsize` field with:

```rust
self._poke24(fptr + mos::FIL_MEMBER_OBJSIZE, file_len as u32);
```

The field is 32 bits and the same hostfs implementation uses `_poke32` for
`FIL.fptr`. A `0x01020305`-byte sparse fixture was consequently reported by
`ffs_fsize` as `0x00020305`; EOF derived from the truncated object size was
also false after a successful seek/read at the true end. The 32-bit
`ffs_flseek`, `ffs_ftell`, and final-byte read paths worked.

The likely correction is `_poke32` at this site, followed by a regression test
with a sparse file larger than `0x00ffffff`. This finding concerns Fab's
directory-hostfs interception, not MOS FatFS on a raw SD image. The project
contract therefore uses the sparse file for 32-bit seek/tell/read evidence and
a small file for size/EOF evidence until Fab is corrected.

## Status

All four findings remain reproducible on the current public pins. PORT-204
therefore retains the three minimal local wrappers and Fab's bounded large-file
workaround. Any future pin change must reproduce each failing shape, prove the
upstream correction, remove only the corresponding shim, and rerun the complete
contract; source inspection alone is insufficient.

For an upstream report, link or attach this file together with
`projects/contract-probe/WRAPPER_AUDIT.md`. The latter defines the structural
audit boundary and prevents the three confirmed defects from being mistaken
for a claim that every libmos wrapper has been semantically qualified.

## AgonDev bundled disassembler: backward relative targets

### AGONDEV-BINUTILS-001 — Backward JR target is displayed 256 bytes too high

BUILD-004 independently reproduced this in the retained ARM64
`ez80-none-elf-objdump`, identifying itself as GNU Binutils 2.45. Executable
SHA-256: `57132e98247a43e0c3bb450ad986592e2c913d5de46bd9ae969ad9ce0310a48e`.
This tool receipt is separate from the older public pins at the top of this
document. Attribution to a particular upstream Binutils/AgonDev source commit
has not been established, and no upstream fix or report submission is claimed.

Minimal assembler input:

```asm
.assume adl=1
.text
.space 8,0
target:
    nop
    jr target
```

Assemble using `ez80-none-elf-as -march=ez80+full+adl`, then inspect with
`ez80-none-elf-objdump -s -d`. The instruction at address 9 is correctly encoded
`18 FD`: signed displacement −3 means `9 + 2 − 3 = 8`. The disassembler prints:

```text
   9: 18 fd    jr 0x0108
```

Expected target is `0x0008`. The existing anonymous-label object test therefore
fails its disassembly-text assertion despite correct output bytes. This is a
diagnostic/display defect in the measured tool, not evidence that GNU as emits
the wrong branch. Wider scope (other instructions/modes/boundaries) is not yet
qualified.

Retained minimal fixture, complete command/output receipts and encoding
regression are indexed in the
[BUILD-004 report](../research/build-004-2026-10-15.md). Its assembly comparison
replays explicit ELF relocations and compares bytes, avoiding reliance on this
display. Do not accept a wrong displayed target merely to make tests pass.
A future corrected tool must pass the minimal fixture and affected regression
before relying on its backward-target disassembly for analysis.

## Stock MOS API repeated number extraction

### MOS-EXTRACTNUMBER-001 — Probe fails on its second invocation in one boot

On 2026-10-16, the unchanged contract probe passed on its first invocation but
reported `CONTRACT-FAIL api-extractnumber-u24-output` on its second invocation
within the same emulator boot. The failure reproduces with both the native
AgonDev candidate and the unmodified official ZDS II v3.0.2 image; their complete
CLI outputs are byte-identical for each matched root-fixture case. It is not a
native-port regression and has not been attributed conclusively to MOS, the
SDK wrapper, the probe, or the emulator.

Measured inputs:

1. Native source `92662538a5766ae1e3d5b47e7dd78829a4dfe1c5`, ROM SHA-256
   `f891721bbb2a0bc2845dbb13edbeb449365a315f11be48500d8e65e2ab1aebb4`.
2. Official v3.0.2 ROM SHA-256
   `d564243283972690933a4554296ad6202ca4ef54572279533a942960846bebae`.
3. Probe SHA-256
   `da8c50487bc32d4c9f8cfa2095bad2f4cf6c772d6498b16d1e724f5eb8c3b9e1`,
   built with the pinned AgonDev toolchain and local wrapper fixes above.
4. Official Fab 1.2.5 commit `c22876d1f7ad903537c308cf65afd6553b37cdb8`;
   CLI SHA-256
   `46dcb512afdbc5a1c5f5d0704a7c02a5197cc8263cb9f3ca9f629e65bb547f44`.

Reproducer: create an empty dedicated directory-backed SD root using
`projects/contract-probe/verify_contract.py`'s `create_fixture(root, binary)`.
Boot either image with that directory as the SD root and send these commands
in the **same** process, without rebooting:

```text
mos-contract-probe.bin
mos-contract-probe.bin
```

The first invocation reports `WRITE-PHASE-CREATE` and `CONTRACT-PASS`. The second
reports the number-extraction failure, `WRITE-PHASE-VERIFY` and
`CONTRACT-FAILED`; MOS then prints `Invalid command` for the probe's nonzero
return. Reproduction is unchanged with zero-filled versus normal initial RAM,
or command names with versus without `.bin`. The numeric assertion uses a small
isolated function, input `"12345"`, flags zero, initially null end pointer and
initially zero result. It expects `FR_OK`, value 12345 and an end pointer five
characters past the start.

Source inspection suggests a stale-state lead: `mos_api_extractnumber` passes
`_scratchpad + 3` as `char **end` without initializing that scratchpad slot;
`extractNumber` reads `*end` to decide whether an explicit endpoint was supplied.
The assembly API documents the endpoint as an output, and the SDK wrapper
does not pass the caller's initially null end-pointer value into this slot.
This is a hypothesis requiring a minimized state/trace experiment, not a
confirmed root cause or an authorized firmware correction. It may also explain
the older frame-sensitivity observation in the probe README, but that connection
is not yet proven.

The normal automated contract remains a **two-cold-boot** test, and passes for
both images. Changing manual review to match that scope does not fix or waive
this separate repeated-run failure. The first manual review additionally used
an incorrectly nested `/native-api` fixture; its path/file failures are a
separate staging error, not evidence of broken filesystem wrappers.

Complete replay script, 16-case matrix, raw logs and corrected cold-boot checks
are retained under `../worktrees/mos-build-005-validation/` and in the dedicated
Oryx profile. No upstream issue was submitted, SDK changed, or MOS fix applied.
