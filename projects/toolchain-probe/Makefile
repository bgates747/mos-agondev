NAME := firmware_probe

TOOLCHAIN ?= $(abspath ../../toolchains/agondev)
TOOLBIN := $(TOOLCHAIN)/bin
TOOLLIB := $(TOOLCHAIN)/lib

CC := $(TOOLBIN)/ez80-none-elf-clang
AS := $(TOOLBIN)/ez80-none-elf-as
LD := $(TOOLBIN)/ez80-none-elf-ld
OBJCOPY := $(TOOLBIN)/ez80-none-elf-objcopy
OBJDUMP := $(TOOLBIN)/ez80-none-elf-objdump
READELF := $(TOOLBIN)/ez80-none-elf-readelf
SIZE := $(TOOLBIN)/ez80-none-elf-size

CPPFLAGS := -nostdinc -isystem $(TOOLCHAIN)/include
CFLAGS := -target ez80-none-elf -march=ez80 \
	-mllvm -z80-gas-style -mllvm -z80-print-zero-offset \
	-Wall -Wextra -Werror -Oz -ffreestanding -fno-builtin \
	-fno-threadsafe-statics -Wa,-march=ez80+full
ASFLAGS := -march=ez80+full+adl
LDFLAGS := -T ld/firmware.ld -Map=bin/$(NAME).map

OBJECTS := obj/reset.o obj/type_model.o obj/hardware_io.o

.DEFAULT_GOAL := all

.PHONY: all clean verify
all: bin/$(NAME).bin

bin/$(NAME).elf: $(OBJECTS) ld/firmware.ld | bin
	$(LD) $(LDFLAGS) -o $@ $(OBJECTS) -L$(TOOLLIB) -l agon

bin/$(NAME).bin: bin/$(NAME).elf
	$(OBJCOPY) -O binary $< $@

obj/%.o: src/%.c | obj
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

obj/%.o: src/%.asm | obj
	$(AS) $(ASFLAGS) -o $@ $<

bin obj:
	mkdir -p $@

verify: bin/$(NAME).bin
	$(READELF) -h -S bin/$(NAME).elf
	$(SIZE) -A bin/$(NAME).elf
	$(OBJDUMP) -dr obj/type_model.o
	sha256sum bin/$(NAME).bin

clean:
	$(RM) -r bin obj
