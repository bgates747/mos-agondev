# Maintained assembly composition shared by the port build and runtime audit.
# Keep the upstream list/order exact; product profiles may only append a
# validated, deterministically sorted suffix.

ASM_SOURCES_EXTRA ?=
ASM_OBJECT_RELATIVE_EXTRA ?=

ASM_SOURCES_BASE := \
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

# Keep unsorted declarations for validation so GNU make's sorting cannot hide
# a duplicate. Only the validated product suffix is sorted for final linkage.
ASM_SOURCES_DECLARED := $(ASM_SOURCES_BASE) $(ASM_SOURCES_EXTRA)
ASM_OBJECT_RELATIVE_BASE := $(ASM_SOURCES_BASE:.asm=.o)
ASM_OBJECT_RELATIVE_DECLARED := $(ASM_OBJECT_RELATIVE_BASE) \
	$(ASM_OBJECT_RELATIVE_EXTRA)
ASM_SOURCES := $(ASM_SOURCES_BASE) $(sort $(ASM_SOURCES_EXTRA))
ASM_OBJECT_RELATIVE := $(ASM_OBJECT_RELATIVE_BASE) \
	$(sort $(ASM_OBJECT_RELATIVE_EXTRA))

ifneq ($(sort $(ASM_OBJECT_RELATIVE_EXTRA)),$(sort $(ASM_SOURCES_EXTRA:.asm=.o)))
$(error ASM_OBJECT_RELATIVE_EXTRA must exactly match ASM_SOURCES_EXTRA with .asm replaced by .o)
endif
