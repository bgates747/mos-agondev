PYTHON ?= $(abspath ../../.venv/bin/python)
TOOLCHAIN ?= ../../toolchains/agondev
MOS_PORT ?= ../mos-port
MOS_SOURCE ?= ../../upstream/agon-mos

.DEFAULT_GOAL := help

.PHONY: help reference reference-check candidate compare check record

help:
	@echo "reference        fetch and hash-check official v3.0.2 release artifacts"
	@echo "reference-check  verify the existing ignored official-artifact cache"
	@echo "candidate        collect disassembly/maps/compiler assembly from the build"
	@echo "compare          generate JSON/Markdown analysis and bounded review queue"
	@echo "check            compare generated results with reviewed evidence"
	@echo "record           replace reviewed evidence after explicit human review"

reference:
	$(PYTHON) -B fetch_reference.py --verify-latest

reference-check:
	$(PYTHON) -B fetch_reference.py --check

candidate:
	$(MAKE) -C $(MOS_PORT) TOOLCHAIN=$(abspath $(TOOLCHAIN)) c-assembly
	$(PYTHON) -B collect_candidate.py \
		--mos-port $(MOS_PORT) --toolchain $(TOOLCHAIN) --source-repo $(MOS_SOURCE)

compare: reference-check candidate
	$(PYTHON) -B analyze.py --toolchain $(TOOLCHAIN) --source-repo $(MOS_SOURCE)

check: compare
	$(PYTHON) -B verify_report.py

record: compare
	$(PYTHON) -B verify_report.py --record
