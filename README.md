# mos-agondev

`mos-agondev` builds ZDS-oriented
[`agon-mos`](https://github.com/AgonPlatform/agon-mos) source with the
[AgonDev](https://github.com/AgonPlatform/agondev) toolchain. The maintained
source keeps its scoped, anonymous, and macro-local assembly idioms; a strict
Python frontend emits disposable GNU-as input during the build.

The first complete candidate compiles all 16 C units, translates and assembles
all 15 active assembly roots, links a restricted firmware runtime, and emits a
fully resolved 102,059-byte MOS image. That image boots with the stock Platform
VDP and has passed bounded shell, hostfs, VDP-protocol, formatter, and MOS API
checks. Broader parity and physical-hardware qualification remain before it can
replace the reference ZDS release build.

Start with [`STARTHERE.md`](STARTHERE.md). It covers fresh-clone setup, the
normal edit/build cycle, optional project-local Fab setup, generated-file
boundaries, and verification levels.

## Fresh clone in brief

The project requires Python 3.14 or newer and uses only the standard library.
In these examples `python3.14` means any executable that reports Python 3.14 or
later; the unqualified `python3` on an otherwise supported system may still be
older:

```bash
python3.14 --version
python3.14 -m venv .venv
```

No `pip install` step is required. Provide an AgonDev checkout containing the
pinned `nightly` source and built `release/` tree described in `STARTHERE.md`,
and a writable `agon-mos` worktree. The default self-contained layout names
them `agondev/` and `agon-mos/` in this repository:

```bash
.venv/bin/python scripts/setup_local.py
.venv/bin/python scripts/prepare_mos_worktree.py
make firmware-check
```

Use `setup_local.py --agondev PATH --agon-mos PATH` instead when the inputs live
elsewhere. The script records them through ignored relative links; it never
modifies either checkout.

Fab Agon Emulator is optional for compilation and `make firmware-check`. It is
required for boot, parity, contract, graphical, and complete `make verify`
gates. The recommended checkout/distribution location is the ignored
`fab-agon-emulator/` directory in this repository. See `STARTHERE.md` for the
complete source-build and profile-setup commands.

## Generated local state

- `toolchains/agondev` points to the configured AgonDev `release/` tree.
- `upstream/agon-mos` points to the configured maintained-source worktree.
- `projects/mos-port/worktree` is a disposable tracked-file copy with exact,
  drift-checked initial portability edits.
- `projects/mos-port/generated` contains disposable GNU-as translation units.
- `emulator` is an isolated Fab profile with stock Platform assets and a local
  writable SD overlay.

The links and generated directories are ignored local state; the target of
`upstream/agon-mos` is the maintained source selected by the developer. Setup
refuses to replace unexpected real files, directories, or links.

## Verification

Useful focused targets are:

```bash
make test
make toolchain-probe
make c-compat-check
make asm-probe
make linker-check
make runtime-check
make firmware-check
make firmware-boot-check
make firmware-parity-check
make vdp-regression-check
make contract-check
make verify
```

`make verify` is the complete portable gate for the currently configured
inputs. `make baseline-check` adds the exact frozen research identities and
measurements from `evidence/baseline.json`; it is for reproducing the original
study, not for every active source edit or every legitimate local Fab rebuild.
Here, portable means checkout-location and locally built-Fab independence; the
pinned AgonDev ABI/runtime contract and the candidate's behavioral regressions
still apply.

## Documentation map

- [`STARTHERE.md`](STARTHERE.md) — current setup and development workflow.
- [`TODO.md`](TODO.md) — the only authoritative list of unfinished work.
- [`docs/README.md`](docs/README.md) — current technical contracts and project
  implementation references.
- [`docs/upstream-findings.md`](docs/upstream-findings.md) — durable reports for
  the AgonDev and Fab maintainers.
- [`research/README.md`](research/README.md) — historical feasibility narrative,
  pinned technical précis, and dated development logs.
- [`evidence/README.md`](evidence/README.md) — frozen machine-readable study
  evidence.

## Emulator qualification

After installing and profiling Fab as described in `STARTHERE.md`, launch the
candidate with:

```bash
make run-custom-emulator
```

If Fab is external, retain the same exported `FAB_ROOT` used during setup or
prefix this Make invocation with it.

Confirm the Platform banner and prompt, keyboard editing, `dir`, `cd bin`,
`help echo`, `time`, `credits`, and `mem`. When `fab-agon-emulator/` is a Git
checkout, confirm it and its SD-card submodule remain clean:

```bash
git -C fab-agon-emulator status --short
git -C fab-agon-emulator/sdcard status --short
```

Use Fab's documented host-side quit shortcut or close its window. Historical
qualification details are in `research/devlog/2026-08-12.md`. Future
emulator-coupled changes require a new human validation and explicit commit
approval.
