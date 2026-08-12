# Upstream findings from the MOS AgonDev port

This document is a durable, shareable report of defects or externally owned
limitations found while porting `agon-mos` to AgonDev. It records evidence; the
project's only actionable work list remains `TODO.md`.

The findings below were reproduced against:

- AgonDev commit `b67ab2444a63267a42193f204889d466765d8dd2`;
- Fab Agon Emulator commit `98bbb392b75b196171cc620b60839220e5ce53ed`;
- `agon-mos` commit `5f67b1ca77eb7a77d3b37cc7b029db51f0d1548e`.

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

The second command runs a read-only AgonDev MOSlet against both the AgonDev-built
MOS and the pinned ZDS MOS. The complete repository gate is `make verify`.

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
deliberately not executed because the target contract uses an immutable hostfs
fixture and does not perform write-side filesystem operations.

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

All four findings are reproducible and remain unmodified upstream. `PORT-204`
tracks coordination, toolchain/emulator pin updates, removal of local shims,
and rerunning the contract after upstream fixes are available.

For an upstream report, link or attach this file together with
`projects/contract-probe/WRAPPER_AUDIT.md`. The latter defines the structural
audit boundary and prevents the three confirmed defects from being mistaken
for a claim that every libmos wrapper has been semantically qualified.
