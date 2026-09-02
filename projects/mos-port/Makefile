UPSTREAM ?= $(abspath worktree)
TOOLCHAIN ?= $(abspath ../../toolchains/agondev)

TOOLBIN := $(TOOLCHAIN)/bin
CC := $(TOOLBIN)/ez80-none-elf-clang
AS := $(TOOLBIN)/ez80-none-elf-as
SIZE := $(TOOLBIN)/ez80-none-elf-size
LD := $(TOOLBIN)/ez80-none-elf-ld
OBJCOPY := $(TOOLBIN)/ez80-none-elf-objcopy
PYTHON ?= $(abspath ../../.venv/bin/python)
PYTHON_ENV ?= $(abspath $(dir $(PYTHON))/..)
REPOSITORY := $(abspath ../..)
ZDS2GAS := tools/zds2gas.py
ASSEMBLE_ZDS := tools/assemble_zds.py
PROVENANCE_TOOL := $(abspath tools/record_target_step.py)
PROVENANCE_DIR ?=
PROVENANCE_DIR_ABS := $(if $(strip $(PROVENANCE_DIR)),$(abspath $(PROVENANCE_DIR)))
GENERATED := generated
PREPARATION_METADATA := $(UPSTREAM)/.mos-agondev-worktree.json

CPPFLAGS := -Iinclude -I$(UPSTREAM)/src -I$(UPSTREAM)/src_fatfs \
	-I$(UPSTREAM)/src_startup -I$(UPSTREAM)/src_umm_malloc \
	-nostdinc -isystem $(TOOLCHAIN)/include \
	-DAGONDEV -D_EZ80 -D_EZ80F92 -DNDEBUG $(CPPFLAGS_EXTRA)
CFLAGS := -target ez80-none-elf -march=ez80 \
	-mllvm -z80-gas-style -mllvm -z80-print-zero-offset \
	-std=gnu17 -Wall -Wextra -Werror=return-type -Oz -ffreestanding \
	-fno-threadsafe-statics -fno-integrated-as -B$(TOOLBIN) \
	-Wa,-march=ez80+full

C_SOURCES_EXTRA ?=
CPPFLAGS_EXTRA ?=
C_SOURCE_CPPFLAGS_RELATIVE ?=
C_SOURCE_CPPFLAGS_EXTRA ?=

include assembly-profile.mk

C_SOURCES_BASE := \
	main.c \
	src/clock.c \
	src/i2c.c \
	src/mos.c \
	src/mos_editor.c \
	src/mos_file.c \
	src/mos_sysvars.c \
	src/strings.c \
	src/tests.c \
	src/timer.c \
	src/uart.c \
	src_fatfs/diskio.c \
	src_fatfs/ff.c \
	src_fatfs/ffsystem.c \
	src_fatfs/ffunicode.c \
	src_umm_malloc/umm_malloc.c

# Source order is part of the linked-image identity. Sorting keeps product
# profile additions deterministic without hard-coding product names here.
C_SOURCES := $(sort $(C_SOURCES_BASE) $(C_SOURCES_EXTRA))

C_OBJECTS := $(addprefix obj/,$(C_SOURCES:.c=.o))
C_ASSEMBLY := $(addprefix inspect/c/,$(C_SOURCES:.c=.s))
C_HEADERS := $(shell find $(UPSTREAM) include -type f -name '*.h' -print | sort)
TOOLCHAIN_INPUTS := $(shell find $(TOOLCHAIN)/include -type f -print | sort)

ifneq ($(strip $(C_SOURCE_CPPFLAGS_EXTRA)),)
ifeq ($(words $(C_SOURCE_CPPFLAGS_RELATIVE)),1)
ifneq ($(findstring %,$(C_SOURCE_CPPFLAGS_RELATIVE)),)
$(error C_SOURCE_CPPFLAGS_RELATIVE must be a literal selected C source, not a Make pattern)
endif
ifeq ($(filter $(C_SOURCE_CPPFLAGS_RELATIVE),$(C_SOURCES)),)
$(error C_SOURCE_CPPFLAGS_RELATIVE is not a selected C source: $(C_SOURCE_CPPFLAGS_RELATIVE))
endif
else
$(error C_SOURCE_CPPFLAGS_RELATIVE must name exactly one selected C source)
endif
endif
ifneq ($(strip $(C_SOURCE_CPPFLAGS_RELATIVE)),)
ifeq ($(strip $(C_SOURCE_CPPFLAGS_EXTRA)),)
$(error C_SOURCE_CPPFLAGS_EXTRA is empty for C_SOURCE_CPPFLAGS_RELATIVE)
endif
endif

ifneq ($(strip $(C_SOURCE_CPPFLAGS_RELATIVE)),)
SCOPED_C_OBJECT := $(addprefix obj/,$(C_SOURCE_CPPFLAGS_RELATIVE:.c=.o))
SCOPED_C_ASSEMBLY := $(addprefix inspect/c/,$(C_SOURCE_CPPFLAGS_RELATIVE:.c=.s))
$(SCOPED_C_OBJECT) $(SCOPED_C_ASSEMBLY): CPPFLAGS += $(C_SOURCE_CPPFLAGS_EXTRA)
endif

ASM_INPUTS := $(shell find $(UPSTREAM)/src $(UPSTREAM)/src_startup \
	-type f \( -name '*.asm' -o -name '*.inc' \) -print | sort)
ASM_OBJECTS := $(addprefix obj/asm/,$(ASM_OBJECT_RELATIVE))
FIRMWARE_OBJECTS := $(ASM_OBJECTS) $(C_OBJECTS)
RUNTIME_ARCHIVE := runtime/build/libmos_runtime.a
RUNTIME_INPUTS := $(shell find runtime -type f \
	! -path 'runtime/build/*' ! -path 'runtime/__pycache__/*' \
	! -path 'runtime/tests/__pycache__/*' -print | sort)
HOSTFS_DESCRIPTOR := obj/hostfs_descriptor.o
FIRMWARE_ELF := bin/MOS.elf
FIRMWARE_BIN := bin/MOS.bin
FIRMWARE_HEX := bin/MOS.hex

ifneq ($(strip $(PROVENANCE_DIR_ABS)),)
PROVENANCE_ROOT_ARGS := \
	--root "BUILD_TOOL=$(REPOSITORY)" \
	--root "BUILD=$(CURDIR)" \
	--root "PREPARED=$(abspath $(UPSTREAM))" \
	--root "TOOLCHAIN=$(abspath $(TOOLCHAIN))" \
	--root "PYTHON_ENV=$(abspath $(PYTHON_ENV))" \
	--root "PROVENANCE=$(PROVENANCE_DIR_ABS)"
C_PROVENANCE_INPUT_ARGS := \
	$(foreach input,$(C_HEADERS) $(TOOLCHAIN_INPUTS) $(PREPARATION_METADATA),--input "$(input)")
ASM_PROVENANCE_INPUTS := $(GENERATED)/manifest.json $(ASSEMBLE_ZDS) $(ZDS2GAS) \
	$(PREPARATION_METADATA) $(addprefix $(GENERATED)/,$(ASM_SOURCES)) \
	$(TOOLCHAIN_INPUTS)
C_PRODUCER_ARGS := $(foreach source,$(C_SOURCES),\
	--producer "obj/$(source:.c=.o)" "$(PROVENANCE_DIR_ABS)/compile/$(source:.c=.json)")
ASM_PRODUCER_ARGS := $(foreach object,$(ASM_OBJECT_RELATIVE),\
	--producer "obj/asm/$(object)" "$(PROVENANCE_DIR_ABS)/assemble/$(object:.o=.json)")
LINK_INPUT_ARGS := $(foreach input,$(FIRMWARE_OBJECTS) $(HOSTFS_DESCRIPTOR) $(RUNTIME_ARCHIVE),\
	--link-input "$(input)")
endif

.DEFAULT_GOAL := firmware

.PHONY: provenance-check profile-assembly-check c-objects c-assembly c-compat \
	asm-sources asm-objects all-objects runtime firmware verify-firmware clean report
provenance-check:
	$(PYTHON) -B $(ZDS2GAS) provenance $(UPSTREAM)

profile-assembly-check:
	$(PYTHON) -B tools/profile_assembly.py --source-root "$(UPSTREAM)" \
		--build-root "$(CURDIR)" --object-root obj/asm \
		$(foreach source,$(ASM_SOURCES_DECLARED),--source=$(source)) \
		$(foreach object,$(ASM_OBJECT_RELATIVE_DECLARED),--object=$(object))

c-objects: provenance-check $(C_OBJECTS)

c-assembly: provenance-check $(C_ASSEMBLY)

c-compat: c-objects
	$(PYTHON) -B verify_c_compat.py --toolchain $(TOOLCHAIN) \
		--worktree $(UPSTREAM) --object-dir obj

asm-sources: $(GENERATED)/manifest.json provenance-check

asm-objects: provenance-check $(ASM_OBJECTS)

all-objects: c-objects asm-objects

runtime: c-objects
	$(MAKE) -C runtime TOOLCHAIN="$(TOOLCHAIN)" PYTHON="$(PYTHON)" \
		PYTHON_ENV="$(PYTHON_ENV)" \
		ASSEMBLY_SOURCE="$(UPSTREAM)" \
		PROVENANCE_DIR="$(PROVENANCE_DIR_ABS)" runtime-archive

firmware: provenance-check $(FIRMWARE_BIN) $(FIRMWARE_HEX) verify-firmware

verify-firmware: $(FIRMWARE_ELF) $(FIRMWARE_BIN)
	$(PYTHON) -B verify_firmware.py $(FIRMWARE_ELF) $(FIRMWARE_BIN) --toolbin $(TOOLBIN)

obj/%.o: $(UPSTREAM)/%.c $(C_HEADERS)
	@mkdir -p $(dir $@)
	if test -n "$(PROVENANCE_DIR_ABS)"; then \
		$(PYTHON) -B $(PROVENANCE_TOOL) \
			--kind c-compile \
			--record "$(PROVENANCE_DIR_ABS)/compile/$*.json" \
			--cwd "$(CURDIR)" $(PROVENANCE_ROOT_ARGS) \
			--source "$<" $(C_PROVENANCE_INPUT_ARGS) \
			--nested-executable "$(AS)" \
			--driver-selected-executable "$(AS)" \
			--output "$@" --depfile "$(@:.o=.d)" -- \
			$(CC) $(CPPFLAGS) $(CFLAGS) -MD -MF "$(@:.o=.d)" -c "$<" -o "$@"; \
	else \
		$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@; \
	fi

inspect/c/%.s: $(UPSTREAM)/%.c $(C_HEADERS)
	@mkdir -p $(dir $@)
	if test -n "$(PROVENANCE_DIR_ABS)"; then \
		$(PYTHON) -B $(PROVENANCE_TOOL) \
			--kind c-assembly \
			--record "$(PROVENANCE_DIR_ABS)/c-assembly/$*.json" \
			--cwd "$(CURDIR)" $(PROVENANCE_ROOT_ARGS) \
			--source "$<" $(C_PROVENANCE_INPUT_ARGS) \
			--output "$@" --depfile "$(@:.s=.d)" -- \
			$(CC) $(CPPFLAGS) $(CFLAGS) -MD -MF "$(@:.s=.d)" -S "$<" -o "$@"; \
	else \
		$(CC) $(CPPFLAGS) $(CFLAGS) -S $< -o $@; \
	fi

# AgonDev 1.0 exhausts registers in FatFS ff.c at its default -Oz level.
# -Os is a verified compiler workaround and supersedes the earlier option.
obj/src_fatfs/ff.o: CFLAGS += -Os
inspect/c/src_fatfs/ff.s: CFLAGS += -Os

# Validation must finish before any prepared-source object recipe can run,
# including under a direct parallel sub-make.
$(C_OBJECTS) $(C_ASSEMBLY): | provenance-check
$(ASM_OBJECTS) $(GENERATED)/manifest.json: | provenance-check profile-assembly-check

$(GENERATED)/manifest.json: $(ZDS2GAS) $(PREPARATION_METADATA) $(ASM_INPUTS)
	$(PYTHON) -B $(ZDS2GAS) tree $(UPSTREAM) $(GENERATED)

obj/asm/%.o: $(GENERATED)/%.asm $(GENERATED)/manifest.json $(ASSEMBLE_ZDS)
	@mkdir -p $(dir $@)
	if test -n "$(PROVENANCE_DIR_ABS)"; then \
		$(PYTHON) -B $(PROVENANCE_TOOL) \
			--kind wrapped-assembly \
			--record "$(PROVENANCE_DIR_ABS)/assemble/$*.json" \
			--cwd "$(CURDIR)" $(PROVENANCE_ROOT_ARGS) \
			--source "$<" \
			$(foreach input,$(filter-out $<,$(ASM_PROVENANCE_INPUTS)),--input "$(input)") \
			--nested-executable "$(AS)" \
			--output "$@" --depfile "$(@:.o=.d)" -- \
			$(PYTHON) -B $(ASSEMBLE_ZDS) \
			--manifest $(GENERATED)/manifest.json --source "$<" --assembler $(AS) -- \
			--MD "$(@:.o=.d)" -march=ez80+full+adl \
			-I $(GENERATED)/src -I $(GENERATED)/src_startup \
			-I $(TOOLCHAIN)/include -o "$@"; \
	else \
	$(PYTHON) -B $(ASSEMBLE_ZDS) \
		--manifest $(GENERATED)/manifest.json --source $< --assembler $(AS) -- \
		-march=ez80+full+adl \
		-I $(GENERATED)/src -I $(GENERATED)/src_startup \
		-I $(TOOLCHAIN)/include -o $@; \
	fi

$(addprefix $(GENERATED)/,$(ASM_SOURCES)): $(GENERATED)/manifest.json

$(HOSTFS_DESCRIPTOR): hostfs_descriptor.asm
	@mkdir -p $(dir $@)
	if test -n "$(PROVENANCE_DIR_ABS)"; then \
		$(PYTHON) -B $(PROVENANCE_TOOL) \
			--kind direct-assembly \
			--record "$(PROVENANCE_DIR_ABS)/assemble/hostfs_descriptor.json" \
			--cwd "$(CURDIR)" $(PROVENANCE_ROOT_ARGS) \
			--source "$<" \
			--output "$@" --depfile "$(@:.o=.d)" -- \
			$(AS) --MD "$(@:.o=.d)" -march=ez80+full+adl "$<" -o "$@"; \
	else \
		$(AS) -march=ez80+full+adl $< -o $@; \
	fi

$(RUNTIME_ARCHIVE): $(C_OBJECTS) $(RUNTIME_INPUTS)
	$(MAKE) -C runtime TOOLCHAIN="$(TOOLCHAIN)" PYTHON="$(PYTHON)" \
		PYTHON_ENV="$(PYTHON_ENV)" \
		ASSEMBLY_SOURCE="$(UPSTREAM)" \
		PROVENANCE_DIR="$(PROVENANCE_DIR_ABS)" runtime-archive

$(FIRMWARE_ELF): $(FIRMWARE_OBJECTS) $(HOSTFS_DESCRIPTOR) $(RUNTIME_ARCHIVE) ld/mos.ld
	@mkdir -p $(dir $@)
	if test -n "$(PROVENANCE_DIR_ABS)"; then \
		$(PYTHON) -B $(PROVENANCE_TOOL) \
			--kind final-link \
			--record "$(PROVENANCE_DIR_ABS)/link/firmware.json" \
			--cwd "$(CURDIR)" $(PROVENANCE_ROOT_ARGS) \
			--source "ld/mos.ld" \
			--output "$@" --depfile "bin/MOS.link.d" \
			--secondary-output "bin/MOS.map" \
			--stdout-file "bin/MOS.link.trace" \
			$(LINK_INPUT_ARGS) $(C_PRODUCER_ARGS) $(ASM_PRODUCER_ARGS) \
			--producer "$(HOSTFS_DESCRIPTOR)" \
				"$(PROVENANCE_DIR_ABS)/assemble/hostfs_descriptor.json" -- \
			$(LD) --orphan-handling=error -T ld/mos.ld -Map bin/MOS.map \
			--dependency-file bin/MOS.link.d --trace \
			-o "$@" $(FIRMWARE_OBJECTS) $(HOSTFS_DESCRIPTOR) $(RUNTIME_ARCHIVE); \
	else \
	$(LD) --orphan-handling=error -T ld/mos.ld -Map bin/MOS.map \
		-o $@ $(FIRMWARE_OBJECTS) $(HOSTFS_DESCRIPTOR) $(RUNTIME_ARCHIVE); \
	fi

$(FIRMWARE_BIN): $(FIRMWARE_ELF)
	$(OBJCOPY) -O binary $< $@

$(FIRMWARE_HEX): $(FIRMWARE_ELF)
	$(OBJCOPY) -O ihex $< $@

report: c-objects
	$(SIZE) -A $(C_OBJECTS)

clean:
	$(RM) -r obj $(GENERATED) inspect bin
	$(MAKE) -C runtime clean
