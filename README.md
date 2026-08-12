# mos-agondev

This repository answers a narrow question: can `agon-mos` be built with
[AgonDev](https://github.com/AgonPlatform/agondev) instead of Zilog ZDS II?

**Conclusion: yes, conditionally—and the first complete image now boots.**
There is no observed eZ80 instruction-set or C ABI blocker. The current build
compiles all 16 C units, translates and assembles all 15 active assembly roots,
links a restricted firmware runtime, and emits a fully resolved 102,059-byte
MOS image. That image boots with the stock Platform VDP, mounts Fab's
directory-backed hostfs, runs shell commands, and matches the pinned ZDS image
across command parsing, process variables, RTC display, credits, nested
read-only hostfs traversal, exact file output, and error handling. Broader
parity and hardware testing are still required before it can replace the
reference release build.

The complete evidence, risks, and recommended sequence are in
[`docs/feasibility-study.md`](docs/feasibility-study.md). Pending work lives only
in [`TODO.md`](TODO.md).

## Local setup

The initial checkout already has a Python 3.14 virtual environment. The project
uses only the standard library, so there are no packages to install. Recreate
the safe local links and generated inputs with:

```bash
.venv/bin/python scripts/setup_local.py
.venv/bin/python scripts/setup_emulator.py
.venv/bin/python scripts/prepare_mos_worktree.py
make verify
```

The generated paths are deliberately ignored:

- `toolchains/agondev` points to the installed AgonDev release.
- `upstream/agon-mos` points to the pinned read-only source checkout.
- `projects/mos-port/worktree` is a disposable tracked-file copy with validated,
  drift-checked initial portability and branch-selection edits.
- `emulator` is an isolated Fab profile with stock Platform MOS/VDP assets and
  a writable local SD overlay.

Neither setup script replaces real files or directories with symlinks. The
upstream repositories are never build or deployment destinations.

## What the probes establish

`projects/toolchain-probe` builds a minimal raw firmware image with reset at
`0x000000`, vectors at `0x000100`, code at `0x000220`, initialized data in ROM
with a RAM VMA, BSS in RAM, and link-time 128 KiB ROM/16 KiB RAM bounds. It also
asserts the Agon ABI type widths and generates code for internal I/O registers.

`projects/mos-port` is the candidate MOS build. Its maintained Python frontend
preserves ZDS scoped, anonymous, and macro-local idioms while generating
disposable GNU-as sources. The production linker fixes reset, vectors, startup,
ROM/RAM copy regions, jump table, heap, and stack; the restricted runtime
excludes AgonDev's application startup and MOS-client wrappers.

Useful focused commands are:

```bash
make toolchain-probe
make c-probe
make c-compat-check
make asm-probe
make linker-check
make runtime-check
make firmware-check
make firmware-boot-check
make firmware-parity-check
make vdp-regression-check
make contract-check
make audit
make test
```

Confirmed issues suitable for reporting to AgonDev and Fab maintainers are in
[`docs/upstream-findings.md`](docs/upstream-findings.md), with executable
reproducers and local corrections under `projects/contract-probe`.

## Emulator qualification

The stock profile has passed its interactive gate. Automated CLI checks now
also boot the custom image, mount hostfs, exercise read-only shell behavior,
and compare stable output with the pinned ZDS build. The linked-byte VDP gate
additionally proves the blocking general-poll startup path and exact
discard/recovery behavior for every oversized one-byte packet length; it uses
the older ZDS binary as an intentional pre-fix negative control.

The custom firmware passed its graphical human gate on 2026-08-12. To repeat
it, run:

```bash
make run-custom-emulator
```

Confirm the Platform banner and prompt, keyboard editing, `dir`, `cd bin`,
`help echo`, `time`, `credits`, and `mem`. Fab documents RightCtrl-Q as its
host-side quit shortcut, although it did not work with the qualification
machine's input stack; closing the emulator window remains sufficient for this
firmware gate. Then confirm the upstream trees remain clean:

```bash
git -C ../../fab-agon-emulator status --short
git -C ../../fab-agon-emulator/sdcard status --short
```

The initial custom-firmware gate and explicit commit approval are recorded in
`docs/devlog-2026-08-12.md`. Future emulator-coupled changes require their own
human qualification and approval before commit.
