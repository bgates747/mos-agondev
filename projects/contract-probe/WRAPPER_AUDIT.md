# Pinned AgonDev libmos wrapper audit

`audit_wrappers.py` audits the read-only AgonDev source tree and the installed
`libagon.a`, then assembles and disassembles the project-local corrections. The
pinned inventory contains 123 `.src` wrappers: 48 use an IX frame, 28 use the
single-argument stack-exchange idiom, 10 delegate to MOS-resident C functions,
and 88 contain a direct `RST.LIL 08h`. Across the framed sources it inventories
126 `(ix+N)` operands.

AgonDev Clang call-site disassembly is generated from `audit/abi_slot_probe.c`.
For `(uint8_t, pointer, uint24_t)`, Clang pushes three three-byte slots; after a
wrapper's `push ix`, their starts are IX+6, IX+9, and IX+12. For
`(uint8_t, uint32_t)`, Clang pushes the 32-bit value as two three-byte words,
then the three-byte first argument. On wrapper entry the handle starts at SP+3
and the low 24 bits of the long start at SP+6.

## Confirmed defects

1. `mos_getError.src` reads the pointer from IX+7 and length from IX+10. Those
   packed offsets point inside the previous three-byte C argument slots; the
   correct starts are IX+9 and IX+12. `src/mos_getError_fixed.asm` is the local
   correction and its runtime behavior is covered by the contract probe.
2. `ffs_setlabel.src` obtains its only pointer argument with `ex (sp),hl`, but
   then overwrites HL with `(ix+6)` without creating an IX frame. The loaded
   address depends on the caller's unrelated IX value. The local correction
   keeps the already-correct HL value and removes the IX read. It is statically
   verified but not invoked because the contract hostfs is intentionally
   read-only.
3. `mos_flseek_p.src` extracts the one-byte handle correctly, then computes
   SP+9 as the address of the following `uint32_t`. SP+9 addresses the upper
   three-byte word; the value's low word begins at SP+6. The local correction
   uses SP+6. The contract probe opens a fixed text file, seeks to offset 3,
   and verifies that the next character is `3` on both firmware images.

The source-wide aligned-slot check finds no other non-three-byte IX offsets.
This is strong evidence against another defect of the exact `mos_getError`
shape, not a semantic proof of every wrapper. The audit separately pins the
only unframed IX user and the only explicit SP-derived argument pointer so new
instances fail rather than disappearing into the inventory.

## Contract-wrapper inventory

The current MOSlet calls `mos_pmatch`, `mos_getleafname`, `mos_getargument`,
`mos_extractstring`, `mos_escapestring`, `mos_getError`, `mos_getabsolutepath`,
`mos_getdirforpath`, `mos_resolvepath`, `mos_isdirectory`, `mos_getrtc`,
`mos_gsinit`, `mos_gsread`, `mos_gstrans`, `mos_substituteargs`, the
simple-handle file API, read-only directory/stat/path/label helpers, the
selected `ffs_*` file API, and `getsysvar_time`. Their assembly wrappers
respectively use aligned frame slots, single-argument stack exchange, corrected
local wrappers, delegated C-ABI tail calls, or no arguments. The audit prints
and pins this coverage set.

`mos_extractnumber` is also a passing runtime assertion, but is intentionally
kept in a small target function. During expansion, the same call inside the
much larger `check_mos_api` frame repeatedly returned 19
(`FR_INVALID_PARAMETER`) with zero/unchanged outputs on the candidate. Once
isolated, the unchanged `"12345"` call returns `FR_OK`, 12345, and the expected
end pointer on both candidate and ZDS reference. This is recorded as an
unresolved probe/compiler frame-sensitivity observation and is not classified
as an AgonDev wrapper or candidate-firmware defect without a minimal
reproducer.

Static source and disassembly cannot validate MOS's register-level RST
semantics, sign/zero extension of every return type, tail-called MOS-resident C
implementations, interrupt callbacks, UART/I2C/SD timing, or hardware. Those
require target execution or hardware evidence. The wrapper audit therefore
does not claim complete libmos ABI qualification.
