RUNTIME_DIR := $(abspath .)
REPOSITORY := $(abspath ../../..)
TOOLCHAIN ?= $(REPOSITORY)/toolchains/agondev
PYTHON ?= $(REPOSITORY)/.venv/bin/python
PYTHON_ENV ?= $(abspath $(dir $(PYTHON))/..)
PROVENANCE_TOOL := $(abspath ../tools/record_target_step.py)
PROVENANCE_DIR ?=
PROVENANCE_DIR_ABS := $(if $(strip $(PROVENANCE_DIR)),$(abspath $(PROVENANCE_DIR)))
HOST_CC ?= cc
C_OBJECT_RELATIVE_EXTRA ?=
ASM_SOURCES_EXTRA ?=
ASM_OBJECT_RELATIVE_EXTRA ?=
ASSEMBLY_SOURCE ?= $(REPOSITORY)/projects/mos-port/worktree

include ../assembly-profile.mk

EZ80_CC := $(TOOLCHAIN)/bin/ez80-none-elf-clang
EZ80_AS := $(TOOLCHAIN)/bin/ez80-none-elf-as
EZ80_LD := $(TOOLCHAIN)/bin/ez80-none-elf-ld
NANOPRINTF_INCLUDE := $(RUNTIME_DIR)/vendor/nanoprintf
BUILD := $(RUNTIME_DIR)/build
C_OBJECT_ROOT := $(REPOSITORY)/projects/mos-port/obj
C_OBJECT_RELATIVE_BASE := \
	main.o \
	src/clock.o \
	src/i2c.o \
	src/mos.o \
	src/mos_editor.o \
	src/mos_file.o \
	src/mos_sysvars.o \
	src/strings.o \
	src/tests.o \
	src/timer.o \
	src/uart.o \
	src_fatfs/diskio.o \
	src_fatfs/ff.o \
	src_fatfs/ffsystem.o \
	src_fatfs/ffunicode.o \
	src_umm_malloc/umm_malloc.o
# Keep this inventory in the same deterministic order as C_SOURCES.
C_OBJECT_RELATIVE := $(sort $(C_OBJECT_RELATIVE_BASE) $(C_OBJECT_RELATIVE_EXTRA))
C_OBJECTS := $(addprefix $(C_OBJECT_ROOT)/,$(C_OBJECT_RELATIVE))
C_OBJECT_EXTRA_ARGS := $(foreach object,$(C_OBJECT_RELATIVE_EXTRA),--c-object $(object))
ASM_SOURCE_ARGS := $(foreach source,$(ASM_SOURCES_DECLARED),--assembly-source $(source))
ASM_OBJECT_ARGS := $(foreach object,$(ASM_OBJECT_RELATIVE_DECLARED),--assembly-object $(object))
ASM_SOURCE_EXTRA_ARGS := $(foreach source,$(ASM_SOURCES_EXTRA),--profile-assembly-source $(source))

EZ80_FLAGS := -target ez80-none-elf -march=ez80 \
	-mllvm -z80-gas-style -mllvm -z80-print-zero-offset \
	-std=gnu17 -Wall -Wextra -Oz -ffreestanding -fno-builtin \
	-fno-threadsafe-statics -Wa,-march=ez80+full \
	-fno-integrated-as -B$(TOOLCHAIN)/bin \
	-nostdinc -isystem $(TOOLCHAIN)/include -iquote$(NANOPRINTF_INCLUDE)
TOOLCHAIN_INPUTS := $(shell find $(TOOLCHAIN)/include -type f -print | sort)

ifneq ($(strip $(PROVENANCE_DIR_ABS)),)
PROVENANCE_ROOT_ARGS := \
	--root "BUILD_TOOL=$(REPOSITORY)" \
	--root "BUILD=$(abspath ..)" \
	--root "PREPARED=$(abspath $(ASSEMBLY_SOURCE))" \
	--root "TOOLCHAIN=$(abspath $(TOOLCHAIN))" \
	--root "PYTHON_ENV=$(abspath $(PYTHON_ENV))" \
	--root "PROVENANCE=$(PROVENANCE_DIR_ABS)"
RUNTIME_C_INPUT_ARGS := $(foreach input,$(NANOPRINTF_INCLUDE)/nanoprintf.h $(TOOLCHAIN_INPUTS),\
	--input "$(input)")
endif

.DEFAULT_GOAL := verify

.PHONY: verify formatter i48-equivalence runtime-archive link-probe audit formats test host-golden clean
verify: test host-golden i48-equivalence audit formats

formatter: $(BUILD)/firmware_printf.o $(BUILD)/i48_required.o

i48-equivalence: formatter
	$(PYTHON) verify_i48_helpers.py

$(BUILD)/firmware_printf.o: formatter/firmware_printf.c $(NANOPRINTF_INCLUDE)/nanoprintf.h
	@mkdir -p $(BUILD)
	if test -n "$(PROVENANCE_DIR_ABS)"; then \
		$(PYTHON) -B $(PROVENANCE_TOOL) \
			--kind c-compile \
			--record "$(PROVENANCE_DIR_ABS)/compile/runtime/firmware_printf.json" \
			--cwd "$(CURDIR)" $(PROVENANCE_ROOT_ARGS) \
			--source "$<" $(RUNTIME_C_INPUT_ARGS) \
			--nested-executable "$(EZ80_AS)" \
			--driver-selected-executable "$(EZ80_AS)" \
			--output "$@" --depfile "$(BUILD)/firmware_printf.d" -- \
			$(EZ80_CC) $(EZ80_FLAGS) -MD -MF "$(BUILD)/firmware_printf.d" \
			-c "$<" -o "$@"; \
	else \
		$(EZ80_CC) $(EZ80_FLAGS) -c $< -o $@; \
	fi

$(BUILD)/i48_required.o: helpers/i48_required.asm
	@mkdir -p $(BUILD)
	if test -n "$(PROVENANCE_DIR_ABS)"; then \
		$(PYTHON) -B $(PROVENANCE_TOOL) \
			--kind direct-assembly \
			--record "$(PROVENANCE_DIR_ABS)/assemble/runtime/i48_required.json" \
			--cwd "$(CURDIR)" $(PROVENANCE_ROOT_ARGS) \
			--source "$<" \
			--output "$@" --depfile "$(BUILD)/i48_required.d" -- \
			$(EZ80_AS) --MD "$(BUILD)/i48_required.d" \
			-march=ez80+full "$<" -o "$@"; \
	else \
		$(EZ80_AS) -march=ez80+full $< -o $@; \
	fi

$(BUILD)/host_golden: formatter/host_golden.c formatter/firmware_printf.c \
	$(NANOPRINTF_INCLUDE)/nanoprintf.h
	@mkdir -p $(BUILD)
	$(HOST_CC) -std=c17 -Wall -Wextra -Werror -fno-builtin \
		-iquote$(NANOPRINTF_INCLUDE) $< -o $@

host-golden: $(BUILD)/host_golden
	$(BUILD)/host_golden

runtime-archive: formatter build_runtime_archive.py runtime_policy.json
	$(PYTHON) build_runtime_archive.py

link-probe: runtime-archive
	$(EZ80_LD) -r -o $(BUILD)/c-runtime-linked.o \
		$(C_OBJECTS) $(BUILD)/libmos_runtime.a

audit: link-probe
	$(PYTHON) audit_runtime.py --assembly "$(ASSEMBLY_SOURCE)" \
		$(C_OBJECT_EXTRA_ARGS) $(ASM_SOURCE_ARGS) $(ASM_OBJECT_ARGS) \
		$(ASM_SOURCE_EXTRA_ARGS)

formats:
	$(PYTHON) scan_formats.py

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	$(RM) -r $(BUILD)
