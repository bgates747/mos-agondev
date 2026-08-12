PYTHON := .venv/bin/python
TOOLCHAIN := $(abspath toolchains/agondev)
MOS_WORKTREE := $(abspath projects/mos-port/worktree)
AGONDEV_SOURCE ?= $(abspath agondev)
MOS_SOURCE ?= $(abspath agon-mos)
FAB_ROOT ?= $(abspath fab-agon-emulator)
AGON_DOCS_ROOT ?= $(abspath agon-docs)
FAB_ROOT_ABS := $(abspath $(FAB_ROOT))

.DEFAULT_GOAL := help

.PHONY: help setup-local setup-emulator prepare-mos worktree-check test audit audit-check \
	check-environment toolchain-probe c-probe probe-output-check emulator-check \
	c-compat-check asm-probe linker-check runtime-check firmware-check firmware-boot-check \
	firmware-parity-check vdp-regression-check vdp-baseline-check contract-check run-custom-emulator \
	binary-reference binary-compare binary-compare-record verify baseline-check clean

.NOTPARALLEL: verify baseline-check firmware-check

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
	@echo "vdp-baseline-check add the pinned ZDS VDP negative control"
	@echo "contract-check     run target formatter and MOS API ABI probes"
	@echo "binary-reference   fetch and hash-check the official release artifacts"
	@echo "binary-compare     automate ZDS-release/AgonDev image comparison"
	@echo "binary-compare-record replace reviewed evidence after inspecting comparison"
	@echo "run-custom-emulator launch the AgonDev-built MOS with stock Platform VDP"
	@echo "audit             print the frozen research source audit as JSON"
	@echo "verify            run portable checks for the configured inputs"
	@echo "baseline-check    add exact frozen research identities and measurements"

setup-local:
	$(PYTHON) scripts/setup_local.py \
		--agondev "$(AGONDEV_SOURCE)" --agon-mos "$(MOS_SOURCE)"

setup-emulator:
	$(PYTHON) scripts/setup_emulator.py --fab-root "$(FAB_ROOT_ABS)"

prepare-mos:
	$(PYTHON) scripts/prepare_mos_worktree.py

worktree-check:
	$(PYTHON) -B scripts/prepare_mos_worktree.py --check

test:
	$(PYTHON) -m unittest discover -s tests -v

audit:
	$(PYTHON) scripts/audit_source.py \
		--fab "$(FAB_ROOT_ABS)" --docs "$(AGON_DOCS_ROOT)"

audit-check:
	$(PYTHON) scripts/audit_source.py \
		--fab "$(FAB_ROOT_ABS)" --docs "$(AGON_DOCS_ROOT)" \
		--check evidence/baseline.json

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

firmware-check: worktree-check asm-probe runtime-check linker-check
	$(MAKE) -C projects/mos-port TOOLCHAIN=$(TOOLCHAIN) \
		UPSTREAM=$(MOS_WORKTREE) firmware

firmware-boot-check: firmware-check emulator-check
	$(PYTHON) -B projects/mos-port/verify_boot.py --fab-root "$(FAB_ROOT_ABS)"

firmware-parity-check: firmware-boot-check
	$(PYTHON) -B projects/mos-port/compare_boot.py --fab-root "$(FAB_ROOT_ABS)"

vdp-regression-check: firmware-check
	$(PYTHON) -B projects/mos-port/verify_vdp_regressions.py

vdp-baseline-check: firmware-boot-check
	$(PYTHON) -B projects/mos-port/verify_vdp_regressions.py \
		--check-reference-negative-control

contract-check: firmware-check emulator-check
	$(MAKE) -C projects/contract-probe AGONDEV_TOOLCHAIN=$(TOOLCHAIN) \
		FAB_ROOT="$(FAB_ROOT_ABS)" clean
	$(MAKE) -C projects/contract-probe AGONDEV_TOOLCHAIN=$(TOOLCHAIN) \
		FAB_ROOT="$(FAB_ROOT_ABS)" verify

binary-reference:
	$(MAKE) -C projects/binary-compare reference

binary-compare: firmware-check
	$(MAKE) -C projects/binary-compare TOOLCHAIN=$(TOOLCHAIN) \
		MOS_SOURCE=$(abspath upstream/agon-mos) check

binary-compare-record: firmware-check
	$(MAKE) -C projects/binary-compare TOOLCHAIN=$(TOOLCHAIN) \
		MOS_SOURCE=$(abspath upstream/agon-mos) record

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
	$(PYTHON) scripts/verify_emulator.py --fab-root "$(FAB_ROOT_ABS)"

verify: test check-environment worktree-check toolchain-probe c-probe c-compat-check asm-probe \
	linker-check runtime-check firmware-check emulator-check \
	firmware-boot-check firmware-parity-check vdp-regression-check contract-check

baseline-check: verify audit-check probe-output-check vdp-baseline-check

clean:
	$(MAKE) -C projects/toolchain-probe clean
	$(MAKE) -C projects/mos-port clean
	$(MAKE) -C projects/contract-probe clean
