# MOS target contract probe

This AgonDev-built MOSlet executes the exact firmware-local formatter source
and a read-only selection of MOS 3.0 API wrappers against both the AgonDev MOS
candidate and the pinned ZDS reference. It covers 24-bit C integers and
pointers, signed and unsigned eight-bit statuses, high-byte 24- and 32-bit
arguments, 32-bit file-position outputs, indirect extended-API dispatch,
multiple pointer outputs, and every formatter spelling used by MOS. The target
MOSlet also exercises read-only string extraction and GS translation state,
argument substitution, six-argument path resolution, simple-handle and
structured file reads, pointer-returning file helpers, stat, directory
enumeration and matching, current-directory lookup, and volume-label lookup.

The pinned wrapper audit identifies three concrete stack-access defects in
`mos_getError`, `ffs_setlabel`, and `mos_flseek_p`. Minimal project-local
corrections and their evidence are described in
[`WRAPPER_AUDIT.md`](WRAPPER_AUDIT.md); they should disappear when the pinned
upstream library is corrected.

Run it through the repository root `make contract-check` target. The verifier
uses a mode-locked, snapshotted temporary directory-backed SD root. A sparse
`0x01020305`-byte file proves high-byte seek/tell and final-byte read paths
without a target write; a small file separately covers size and EOF. Fab's
current hostfs open hook stores `FIL.obj.objsize` with a 24-bit write, so a
greater-than-16-MiB `fsize`/`feof` assertion would test an emulator limitation,
not either MOS image. Fixture hashes must remain identical after each firmware
run. The verifier requires identical sentinel output from both images. It does
not exercise UART, interrupt callback ABIs, write-side FatFS, graphical
keyboard input, or physical hardware. It likewise does not claim every
possible 24-bit return value: the read wrappers are checked for their full
C-declared return type but with an 18-byte fixture, while high-byte value paths
are covered separately by argument and 32-bit file-position tests.

`mos_extractnumber` is deliberately isolated in a small target function. While
the probe was being expanded, putting the same call inside the much larger
`check_mos_api` frame repeatedly made the candidate report
`FR_INVALID_PARAMETER` (19) with zero/unchanged outputs. Moving the unchanged
`"12345"` call into its own frame makes both candidate and ZDS reference return
`FR_OK`, the 24-bit value 12345, and the expected end pointer. This is an
unresolved probe/compiler frame-sensitivity observation, not a confirmed MOS
or AgonDev wrapper defect; the small-frame candidate/reference assertion
remains in the normal contract run and PORT-202 retains the investigation.
