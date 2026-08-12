# mos-agondev project handoff

Read `../agon-dev-env/codex/AGENTS.md` before working
here. This repository is an isolated feasibility study and port scaffold; the
checkouts reached through `upstream/` and `toolchains/` are read-only inputs.

## Current state

The study concludes that an AgonDev MOS port is technically feasible, with
medium-high implementation risk until a complete image boots. The repository
does not yet contain a bootable replacement MOS. It contains a firmware-layout
toolchain proof, an all-C compile probe, source-audit tooling, and a generated
stock Platform MOS/VDP emulator profile.

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

Run `make verify` for the automated qualification available at this stage.
This does not qualify emulator behavior or a future firmware image.

## Emulator gate

Every emulator-coupled change must remain uncommitted and unpushed until the
user runs `scripts/run_emulator.sh`, verifies the interactive behavior described
in the README, and explicitly approves committing it. Automated verification
does not waive this gate.
