# mos-agondev project handoff

Read `../agon-dev-env/codex/AGENTS.md` before working
here. This repository is an isolated feasibility study and port scaffold; the
checkouts reached through `upstream/` and `toolchains/` are read-only inputs.

## Current state

The study concludes that an AgonDev MOS port is technically feasible. The first
complete candidate now builds and boots: all C and active assembly inputs link
with a restricted runtime into a verified 102,059-byte image, and headless Fab
tests reach the shell with directory-backed hostfs. It is still a candidate,
not a replacement release, until broader parity and hardware qualification.

`TODO.md` is the only authoritative task list. The current technical conclusion
is in `docs/feasibility-study.md`; verified platform facts are in
`docs/technical-precis.md`; the selected assembly frontend direction is in
`docs/assembly-compatibility-strategy.md`; chronological work is in the latest
dated dev log.

## Session start

Use only `.venv/bin/python` for project Python commands. Recreate local links
and generated state with:

```bash
.venv/bin/python scripts/setup_local.py
.venv/bin/python scripts/setup_emulator.py
.venv/bin/python scripts/prepare_mos_worktree.py
```

The worktree preparation command intentionally refuses to replace an existing
generated worktree. Upstream `agon-mos`, AgonDev, and Fab emulator checkouts must
remain unchanged.

Run `make verify` for unit, source, compiler, linker, runtime, complete-image,
headless boot, hostfs, and limited ZDS-reference parity checks.

## Emulator gate

Every emulator-coupled change must remain uncommitted and unpushed until the
user runs the appropriate launcher and explicitly approves committing it. For
the current custom firmware batch, use `make run-custom-emulator` and follow the
README checklist. Automated verification does not waive this gate.
