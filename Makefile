PYTHON := .venv/bin/python
TOOLCHAIN := $(abspath toolchains/agondev)
MOS_WORKTREE := $(abspath projects/mos-port/worktree)

.DEFAULT_GOAL := help

.PHONY: help setup-local setup-emulator prepare-mos worktree-check test audit audit-check \
	check-environment toolchain-probe c-probe probe-output-check emulator-check \
	c-compat-check asm-probe linker-check runtime-check firmware-check firmware-boot-check \
	firmware-parity-check vdp-regression-check contract-check run-custom-emulator verify clean

.NOTPARALLEL: verify firmware-check

help:
	@echo "setup-local       create safe links to read-only source/toolchain inputs"
	@echo "setup-emulator    create the ignored stock Platform emulator profile"
	@echo "prepare-mos       create the ignored C-probe worktree (refuses overwrite)"
	@echo "worktree-check    verify the generated MOS worktree byte-for-byte"
	@echo "toolchain-probe   build and inspect the fixed-layout firmware proof"
	@echo "c-probe           compile all MOS C translation units"
	@echo "c-compat-check    audit the MOS C/header/ABI compatibility contract"
	@echo "asm-probe         translate and assemble all MOS assembly units"
	@echo "linker-check      exercise production firmware layout assertions"
	@echo "runtime-check     audit the allow-listed firmware runtime"
	@echo "firmware-check    build and verify a fully resolved MOS image"
	@echo "firmware-boot-check boot the custom image and exercise directory-backed SD"
	@echo "firmware-parity-check compare safe shell output with the ZDS image"
	@echo "vdp-regression-check execute linked VDP handshake/oversize regressions"
	@echo "contract-check     run target formatter and MOS API ABI probes"
	@echo "run-custom-emulator launch the AgonDev-built MOS with stock Platform VDP"
	@echo "audit             print the source/baseline audit as JSON"
	@echo "verify            run all non-interactive checks"

setup-local:
	$(PYTHON) scripts/setup_local.py

setup-emulator:
	$(PYTHON) scripts/setup_emulator.py

prepare-mos:
	$(PYTHON) scripts/prepare_mos_worktree.py

worktree-check:
	$(PYTHON) -B scripts/prepare_mos_worktree.py --check

test:
	$(PYTHON) -m unittest discover -s tests -v

audit:
	$(PYTHON) scripts/audit_source.py

audit-check:
	$(PYTHON) scripts/audit_source.py --check evidence/baseline.json

check-environment:
	$(PYTHON) scripts/verify_environment.py

toolchain-probe:
	$(MAKE) -C projects/toolchain-probe TOOLCHAIN=$(TOOLCHAIN) clean
	$(MAKE) -C projects/toolchain-probe TOOLCHAIN=$(TOOLCHAIN) all verify

c-probe:
	$(MAKE) -C projects/mos-port TOOLCHAIN=$(TOOLCHAIN) \
		UPSTREAM=$(MOS_WORKTREE) clean
	$(MAKE) -C projects/mos-port TOOLCHAIN=$(TOOLCHAIN) \
		UPSTREAM=$(MOS_WORKTREE) c-objects report

c-compat-check: c-probe
	$(MAKE) -C projects/mos-port TOOLCHAIN=$(TOOLCHAIN) \
		UPSTREAM=$(MOS_WORKTREE) c-compat

asm-probe:
	$(MAKE) -C projects/mos-port TOOLCHAIN=$(TOOLCHAIN) \
		UPSTREAM=$(MOS_WORKTREE) asm-objects

linker-check:
	$(PYTHON) -B projects/mos-port/ld/verify_linker.py

runtime-check: c-probe
	$(MAKE) -C projects/mos-port/runtime verify

firmware-check: asm-probe runtime-check linker-check
	$(MAKE) -C projects/mos-port TOOLCHAIN=$(TOOLCHAIN) \
		UPSTREAM=$(MOS_WORKTREE) firmware

firmware-boot-check: firmware-check emulator-check
	$(PYTHON) -B projects/mos-port/verify_boot.py

firmware-parity-check: firmware-boot-check
	$(PYTHON) -B projects/mos-port/compare_boot.py

vdp-regression-check: firmware-boot-check
	$(PYTHON) -B projects/mos-port/verify_vdp_regressions.py

contract-check: firmware-check emulator-check
	$(MAKE) -C projects/contract-probe AGONDEV_TOOLCHAIN=$(TOOLCHAIN) clean
	$(MAKE) -C projects/contract-probe AGONDEV_TOOLCHAIN=$(TOOLCHAIN) verify

run-custom-emulator: firmware-check emulator-check
	@cd emulator && exec ./fab-agon-emulator \
		--renderer sw \
		--firmware platform \
		--mos ../projects/mos-port/bin/MOS.bin \
		--sdcard ./sdcard \
		--verbose -z

probe-output-check:
	$(PYTHON) scripts/verify_probe_outputs.py

emulator-check:
	$(PYTHON) scripts/verify_emulator.py

verify: test check-environment worktree-check audit-check toolchain-probe c-probe c-compat-check asm-probe \
	linker-check runtime-check firmware-check probe-output-check emulator-check \
	firmware-boot-check firmware-parity-check vdp-regression-check contract-check

clean:
	$(MAKE) -C projects/toolchain-probe clean
	$(MAKE) -C projects/mos-port clean
	$(MAKE) -C projects/contract-probe clean
