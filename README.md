# mos-agondev

This repository answers a narrow question: can `agon-mos` be built with
[AgonDev](https://github.com/AgonPlatform/agondev) instead of Zilog ZDS II?

**Conclusion: yes, conditionally.** There is no observed eZ80 instruction-set
or C ABI blocker. AgonDev successfully produced a fixed-address ADL firmware
probe, and all 16 MOS C translation units generated objects after five small
portability edits and a per-file `-Os` workaround for FatFS. This is not a
Makefile-only migration: about 6,680 lines of ZDS assembly/include source,
firmware startup and linking, hardware-register headers, and the selected C
runtime still need a deliberate port. Risk is medium-high until a full image
boots and exercises the MOS APIs.

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
- `projects/mos-port/worktree` is a disposable tracked-file copy with the five
  validated C-probe edits.
- `emulator` is an isolated Fab profile with stock Platform MOS/VDP assets and
  a writable local SD overlay.

Neither setup script replaces real files or directories with symlinks. The
upstream repositories are never build or deployment destinations.

## What the probes establish

`projects/toolchain-probe` builds a minimal raw firmware image with reset at
`0x000000`, vectors at `0x000100`, code at `0x000220`, initialized data in ROM
with a RAM VMA, BSS in RAM, and link-time 128 KiB ROM/16 KiB RAM bounds. It also
asserts the Agon ABI type widths and generates code for internal I/O registers.

`projects/mos-port` compiles every current MOS C translation unit. It is not a
MOS build: the assembly, startup, interrupt vectors, hardware routines, and
firmware-safe runtime policy remain intentionally unresolved.

Useful focused commands are:

```bash
make toolchain-probe
make c-probe
make audit
make test
```

## Stock emulator qualification

Automated checks validate the local profile's paths, stock hashes, shared
libraries, and command-line support. Interactive behavior still requires a
human check:

```bash
scripts/run_emulator.sh
```

Confirm that verbose output selects `mos_platform.bin`, `vdp_platform.so`, and
the project-local `sdcard`; that the Platform banner and prompt appear; that
keyboard input works; and that RightCtrl-Q exits. Then confirm both emulator
source trees remain clean:

```bash
git -C ../../fab-agon-emulator status --short
git -C ../../fab-agon-emulator/sdcard status --short
```

Per the local Agon conventions, this repository remains uncommitted until that
human emulator gate is passed and the user explicitly approves a commit.
