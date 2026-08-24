RUNTIME_DIR := $(abspath .)
REPOSITORY := $(abspath ../../..)
TOOLCHAIN ?= $(REPOSITORY)/toolchains/agondev
PYTHON ?= $(REPOSITORY)/.venv/bin/python
HOST_CC ?= cc
C_OBJECT_RELATIVE_EXTRA ?=

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

EZ80_FLAGS := -target ez80-none-elf -march=ez80 \
	-mllvm -z80-gas-style -mllvm -z80-print-zero-offset \
	-std=gnu17 -Wall -Wextra -Oz -ffreestanding -fno-builtin \
	-fno-threadsafe-statics -Wa,-march=ez80+full \
	-nostdinc -isystem $(TOOLCHAIN)/include -iquote$(NANOPRINTF_INCLUDE)

.DEFAULT_GOAL := verify

.PHONY: verify formatter i48-equivalence runtime-archive link-probe audit formats test host-golden clean
verify: test host-golden i48-equivalence audit formats

formatter: $(BUILD)/firmware_printf.o $(BUILD)/i48_required.o

i48-equivalence: formatter
	$(PYTHON) verify_i48_helpers.py

$(BUILD)/firmware_printf.o: formatter/firmware_printf.c $(NANOPRINTF_INCLUDE)/nanoprintf.h
	@mkdir -p $(BUILD)
	$(EZ80_CC) $(EZ80_FLAGS) -c $< -o $@

$(BUILD)/i48_required.o: helpers/i48_required.asm
	@mkdir -p $(BUILD)
	$(EZ80_AS) -march=ez80+full $< -o $@

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
	$(PYTHON) audit_runtime.py $(C_OBJECT_EXTRA_ARGS)

formats:
	$(PYTHON) scan_formats.py

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	$(RM) -r $(BUILD)
