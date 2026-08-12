UPSTREAM ?= $(abspath worktree)
TOOLCHAIN ?= $(abspath ../../toolchains/agondev)

TOOLBIN := $(TOOLCHAIN)/bin
CC := $(TOOLBIN)/ez80-none-elf-clang
SIZE := $(TOOLBIN)/ez80-none-elf-size

CPPFLAGS := -Iinclude -I$(UPSTREAM)/src -I$(UPSTREAM)/src_fatfs \
	-I$(UPSTREAM)/src_startup -I$(UPSTREAM)/src_umm_malloc \
	-nostdinc -isystem $(TOOLCHAIN)/include \
	-DAGONDEV -D_EZ80 -D_EZ80F92 -DNDEBUG
CFLAGS := -target ez80-none-elf -march=ez80 \
	-mllvm -z80-gas-style -mllvm -z80-print-zero-offset \
	-std=gnu17 -Wall -Wextra -Wno-return-type -Oz -ffreestanding \
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

.DEFAULT_GOAL := c-objects

.PHONY: c-objects clean report
c-objects: $(C_OBJECTS)

obj/%.o: $(UPSTREAM)/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

# AgonDev 1.0 exhausts registers in FatFS ff.c at its default -Oz level.
# -Os is a verified compiler workaround and supersedes the earlier option.
obj/src_fatfs/ff.o: CFLAGS += -Os

report: c-objects
	$(SIZE) -A $(C_OBJECTS)

clean:
	$(RM) -r obj
