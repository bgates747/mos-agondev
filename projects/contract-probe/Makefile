NAME := mos-contract-probe

REPOSITORY := $(abspath ../..)
AGONDEV_TOOLCHAIN ?= $(REPOSITORY)/toolchains/agondev
LDHAS_ARG_PROCESSING := 0
LDHAS_EXIT_HANDLER := 0

include $(AGONDEV_TOOLCHAIN)/config/makefile.inc

FORMATTER_DIR := ../mos-port/runtime/formatter
NANOPRINTF_DIR := ../mos-port/runtime/vendor/nanoprintf
FORMATTER_OBJECT := $(OBJDIR)/firmware_printf.o
PYTHON := $(REPOSITORY)/.venv/bin/python
FAB_ROOT ?= $(REPOSITORY)/fab-agon-emulator
OBJS += $(FORMATTER_OBJECT)
CFLAGS += -std=gnu17 -Wall -Wextra -Werror -fno-builtin

$(LINKBINARY): $(FORMATTER_OBJECT)

$(FORMATTER_OBJECT): $(FORMATTER_DIR)/firmware_printf.c \
		$(NANOPRINTF_DIR)/nanoprintf.h
	@echo [compiling firmware formatter contract]
	@mkdir -p $(dir $@)
	$(V)$(CC) $(CFLAGS) -iquote$(NANOPRINTF_DIR) -c $< -o $@

.PHONY: audit verify
audit:
	$(PYTHON) -B -m unittest discover -s audit/tests -v
	$(PYTHON) -B audit_wrappers.py

verify: audit all
	$(PYTHON) -B verify_contract.py --fab-root "$(FAB_ROOT)"
