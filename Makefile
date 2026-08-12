PYTHON := .venv/bin/python
TOOLCHAIN := $(abspath toolchains/agondev)
MOS_WORKTREE := $(abspath projects/mos-port/worktree)

.DEFAULT_GOAL := help

.PHONY: help setup-local setup-emulator prepare-mos test audit audit-check \
	check-environment toolchain-probe c-probe probe-output-check emulator-check \
	verify clean

help:
	@echo "setup-local       create safe links to read-only source/toolchain inputs"
	@echo "setup-emulator    create the ignored stock Platform emulator profile"
	@echo "prepare-mos       create the ignored C-probe worktree (refuses overwrite)"
	@echo "toolchain-probe   build and inspect the fixed-layout firmware proof"
	@echo "c-probe           compile all MOS C translation units"
	@echo "audit             print the source/baseline audit as JSON"
	@echo "verify            run all non-interactive checks"

setup-local:
	$(PYTHON) scripts/setup_local.py

setup-emulator:
	$(PYTHON) scripts/setup_emulator.py

prepare-mos:
	$(PYTHON) scripts/prepare_mos_worktree.py

test:
	$(PYTHON) -m unittest discover -s tests -v

audit:
	$(PYTHON) scripts/audit_source.py

audit-check:
	$(PYTHON) scripts/audit_source.py --check evidence/baseline.json

check-environment:
	$(PYTHON) scripts/verify_environment.py

toolchain-probe:
	$(MAKE) -C projects/toolchain-probe TOOLCHAIN=$(TOOLCHAIN) clean all verify

c-probe:
	$(MAKE) -C projects/mos-port TOOLCHAIN=$(TOOLCHAIN) \
		UPSTREAM=$(MOS_WORKTREE) clean c-objects report

probe-output-check:
	$(PYTHON) scripts/verify_probe_outputs.py

emulator-check:
	$(PYTHON) scripts/verify_emulator.py

verify: test check-environment audit-check toolchain-probe c-probe \
	probe-output-check emulator-check

clean:
	$(MAKE) -C projects/toolchain-probe clean
	$(MAKE) -C projects/mos-port clean
