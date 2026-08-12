UPSTREAM ?= $(abspath worktree)
TOOLCHAIN ?= $(abspath ../../toolchains/agondev)

TOOLBIN := $(TOOLCHAIN)/bin
CC := $(TOOLBIN)/ez80-none-elf-clang
AS := $(TOOLBIN)/ez80-none-elf-as
SIZE := $(TOOLBIN)/ez80-none-elf-size
LD := $(TOOLBIN)/ez80-none-elf-ld
OBJCOPY := $(TOOLBIN)/ez80-none-elf-objcopy
PYTHON ?= $(abspath ../../.venv/bin/python)
ZDS2GAS := tools/zds2gas.py
ASSEMBLE_ZDS := tools/assemble_zds.py
GENERATED := generated
BASELINE := ../../evidence/baseline.json

CPPFLAGS := -Iinclude -I$(UPSTREAM)/src -I$(UPSTREAM)/src_fatfs \
	-I$(UPSTREAM)/src_startup -I$(UPSTREAM)/src_umm_malloc \
	-nostdinc -isystem $(TOOLCHAIN)/include \
	-DAGONDEV -D_EZ80 -D_EZ80F92 -DNDEBUG
CFLAGS := -target ez80-none-elf -march=ez80 \
	-mllvm -z80-gas-style -mllvm -z80-print-zero-offset \
	-std=gnu17 -Wall -Wextra -Werror=return-type -Oz -ffreestanding \
	-fno-threadsafe-statics -Wa,-march=ez80+full

C_SOURCES := \
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

C_OBJECTS := $(addprefix obj/,$(C_SOURCES:.c=.o))
C_HEADERS := $(shell find $(UPSTREAM) include -type f -name '*.h' -print | sort)

ASM_SOURCES := \
	src/crash.asm \
	src/gpio.asm \
	src/interrupts.asm \
	src/keyboard.asm \
	src/misc.asm \
	src/mos_api.asm \
	src/rtc.asm \
	src/sd.asm \
	src/serial.asm \
	src/spi.asm \
	src/vdp_protocol.asm \
	src_startup/cstartup.asm \
	src_startup/globals.asm \
	src_startup/init_params_f92.asm \
	src_startup/vectors16.asm

ASM_INPUTS := $(shell find $(UPSTREAM)/src $(UPSTREAM)/src_startup \
	-type f \( -name '*.asm' -o -name '*.inc' \) -print | sort)
ASM_OBJECTS := $(addprefix obj/asm/,$(ASM_SOURCES:.asm=.o))
FIRMWARE_OBJECTS := $(ASM_OBJECTS) $(C_OBJECTS)
RUNTIME_ARCHIVE := runtime/build/libmos_runtime.a
RUNTIME_INPUTS := $(shell find runtime -type f \
	! -path 'runtime/build/*' ! -path 'runtime/__pycache__/*' \
	! -path 'runtime/tests/__pycache__/*' -print | sort)
HOSTFS_DESCRIPTOR := obj/hostfs_descriptor.o
FIRMWARE_ELF := bin/MOS.elf
FIRMWARE_BIN := bin/MOS.bin
FIRMWARE_HEX := bin/MOS.hex

.DEFAULT_GOAL := firmware

.PHONY: c-objects c-compat asm-sources asm-objects all-objects runtime firmware verify-firmware clean report
c-objects: $(C_OBJECTS)

c-compat: c-objects
	$(PYTHON) -B verify_c_compat.py --toolchain $(TOOLCHAIN) \
		--worktree $(UPSTREAM) --object-dir obj

asm-sources: $(GENERATED)/manifest.json

asm-objects: $(ASM_OBJECTS)

all-objects: c-objects asm-objects

runtime: c-objects
	$(MAKE) -C runtime runtime-archive

firmware: $(FIRMWARE_BIN) $(FIRMWARE_HEX) verify-firmware

verify-firmware: $(FIRMWARE_ELF) $(FIRMWARE_BIN)
	$(PYTHON) -B verify_firmware.py $(FIRMWARE_ELF) $(FIRMWARE_BIN) --toolbin $(TOOLBIN)

obj/%.o: $(UPSTREAM)/%.c $(C_HEADERS)
	@mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

# AgonDev 1.0 exhausts registers in FatFS ff.c at its default -Oz level.
# -Os is a verified compiler workaround and supersedes the earlier option.
obj/src_fatfs/ff.o: CFLAGS += -Os

$(GENERATED)/manifest.json: $(ZDS2GAS) $(BASELINE) $(ASM_INPUTS)
	$(PYTHON) -B $(ZDS2GAS) tree $(UPSTREAM) $(GENERATED)

obj/asm/%.o: $(GENERATED)/%.asm $(GENERATED)/manifest.json $(ASSEMBLE_ZDS)
	@mkdir -p $(dir $@)
	$(PYTHON) -B $(ASSEMBLE_ZDS) \
		--manifest $(GENERATED)/manifest.json --source $< --assembler $(AS) -- \
		-march=ez80+full+adl \
		-I $(GENERATED)/src -I $(GENERATED)/src_startup \
		-I $(TOOLCHAIN)/include -o $@

$(addprefix $(GENERATED)/,$(ASM_SOURCES)): $(GENERATED)/manifest.json

$(HOSTFS_DESCRIPTOR): hostfs_descriptor.asm
	@mkdir -p $(dir $@)
	$(AS) -march=ez80+full+adl $< -o $@

$(RUNTIME_ARCHIVE): $(C_OBJECTS) $(RUNTIME_INPUTS)
	$(MAKE) -C runtime runtime-archive

$(FIRMWARE_ELF): $(FIRMWARE_OBJECTS) $(HOSTFS_DESCRIPTOR) $(RUNTIME_ARCHIVE) ld/mos.ld
	@mkdir -p $(dir $@)
	$(LD) --orphan-handling=error -T ld/mos.ld -Map bin/MOS.map \
		-o $@ $(FIRMWARE_OBJECTS) $(HOSTFS_DESCRIPTOR) $(RUNTIME_ARCHIVE)

$(FIRMWARE_BIN): $(FIRMWARE_ELF)
	$(OBJCOPY) -O binary $< $@

$(FIRMWARE_HEX): $(FIRMWARE_ELF)
	$(OBJCOPY) -O ihex $< $@

report: c-objects
	$(SIZE) -A $(C_OBJECTS)

clean:
	$(RM) -r obj $(GENERATED) bin
	$(MAKE) -C runtime clean
