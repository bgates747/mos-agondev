# MOS AgonDev port workspace

This directory contains the implementation toward an AgonDev-built MOS image.
It is not yet a qualified firmware release.

`scripts/prepare_mos_worktree.py` copies only Git-tracked files from the
read-only upstream checkout into ignored `worktree/`, then applies validated,
drift-checked initial-port edits. `include/ez80.h` is an audited facade over
AgonDev's official `ez80f92.h`: only the hardware names used by MOS are turned
into ZDS-compatible register lvalues, using AgonDev's address-space I/O. The
type aliases, exact official-header dependency set, hardware addresses,
generated instructions, `quickrand` ABI return, and FAT timestamp shift are
enforced by `c_compat_contract.json` and `verify_c_compat.py`.

From the repository root:

```bash
.venv/bin/python scripts/prepare_mos_worktree.py
make c-probe
make c-compat-check
make asm-probe
```

All 16 C translation units compile. FatFS `ff.c` has a local `-Os` override
because this AgonDev version exhausts registers for that file at `-Oz`. The
ongoing compatibility frontend under `tools/` translates all 20 assembly and
include files, and all 15 build-critical units assemble. The production linker
contract and firmware runtime are separately verified under `ld/` and
`runtime/`. Together they produce a fully resolved ELF, GNU map, 102,059-byte
binary, and Intel HEX. The image contains Fab's format-2 descriptor, boots with
the stock Platform VDP, mounts the local hostfs SD root, and passes the initial
read-only shell comparison with the pinned ZDS image. Broader parity, the
graphical human gate, and hardware qualification remain.

The root targets `firmware-check`, `firmware-boot-check`,
`firmware-parity-check`, `vdp-regression-check`, and `run-custom-emulator`
cover successive gates.
The exact scope and remaining gaps of the deterministic CLI comparison are in
[`PARITY.md`](PARITY.md).
