# mos-agondev project handoff

This file is the self-contained project handoff. When this checkout is inside
the author's larger Agon workspace and `../agon-dev-env/codex/AGENTS.md` exists,
read that shared guidance first. An independent clone does not require it.

The checkouts reached through `upstream/` and `toolchains/` are inputs. Treat
them as read-only unless the selected MOS checkout is explicitly a
developer-owned worktree being edited under the workflow in `STARTHERE.md`.

Read `OWNERSHIP.md` before changing source selection, preparation, translation,
runtime, candidate profiles, qualification evidence, or task ownership.

## Current state

The study concludes that an AgonDev MOS port is technically feasible. The first
complete candidate now builds and boots: all C and active assembly inputs link
with a restricted runtime into a verified 102,059-byte image, and headless Fab
tests reach the shell with directory-backed hostfs. It is still a candidate,
not a replacement release, until broader parity and hardware qualification.
The official-release binary comparison is reproducible through
`make binary-reference` and `make binary-compare`; do not record new evidence
until its generated report and bounded queue have been reviewed.

`TODO.md` is the only authoritative task list. Current setup is in
`STARTHERE.md`; current technical documents are indexed by `docs/README.md`;
the original feasibility narrative, pinned précis, and dated logs are indexed
by `research/README.md`.

## Session start

Create the project interpreter when it is absent, then use only that interpreter
for project Python commands. Prepare the copied MOS tree only when it is absent;
otherwise verify it:

```bash
python3.14 -m venv .venv
```

When `toolchains/agondev` or `upstream/agon-mos` is absent, configure it once
with `scripts/setup_local.py` and the project-local defaults or the explicit
source paths documented in `STARTHERE.md`. Do not rerun the no-argument setup
against an existing external-path configuration.

Run `.venv/bin/python scripts/prepare_mos_worktree.py` when
`projects/mos-port/worktree` is absent. When it already exists, run the same
command with `--check` instead.

Fab is optional for compilation. When emulator gates are in scope, install it
at `fab-agon-emulator/` and run
`.venv/bin/python scripts/setup_emulator.py`. For an external installation,
export `FAB_ROOT=PATH_TO_FAB` for the session. Then use `make setup-emulator`
and retain the variable for every later emulator Make target.

The worktree preparation command intentionally refuses to replace an existing
generated worktree. Preparation and builds never change their configured
inputs. Reference-owned checkouts remain read-only; a developer-owned
`agon-mos` worktree is edited only through the maintained-source workflow in
`STARTHERE.md`.

Run `make verify` for unit, source, compiler, linker, runtime, complete-image,
headless boot, hostfs, and limited ZDS-reference parity checks.

Build maintained MOS products through the repository-root `firmware-check` or
`verify` target so every `FIRMWARE_LINK_CHECKS` entry owned by the selected
source profile runs against the final ELF. Do not treat a direct
`projects/mos-port` build as a qualified product build. Fab exchanges complete
UART bytes without an independently clocked VDP endpoint, so emulator success
does not validate a programmed baud divisor or physical UART timing.

## Emulator gate

Every emulator-coupled change must remain uncommitted and unpushed until the
user runs the appropriate launcher and explicitly approves committing it. Use
`make run-custom-emulator` (with the same exported `FAB_ROOT` when Fab is
external) and follow the README checklist. Automated verification does not
waive this gate.
