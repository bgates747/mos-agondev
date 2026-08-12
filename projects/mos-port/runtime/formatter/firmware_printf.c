/*
 * Firmware-local printf/sprintf binding for the Agon MOS port.
 *
 * This translation unit intentionally does not include <stdio.h> and must not
 * be replaced by libagon.a's nanoprintf.o. That archive member also carries
 * application-facing putchar/fputc references. The maintained MOS assembly
 * exports _putch, which is the raw UART/VDP byte sink required here.
 */

#include <limits.h>
#include <stdarg.h>
#include <stddef.h>

#define NANOPRINTF_USE_FIELD_WIDTH_FORMAT_SPECIFIERS 1
#define NANOPRINTF_USE_PRECISION_FORMAT_SPECIFIERS 1
#define NANOPRINTF_USE_FLOAT_FORMAT_SPECIFIERS 0
#define NANOPRINTF_USE_LARGE_FORMAT_SPECIFIERS 0
#define NANOPRINTF_USE_SMALL_FORMAT_SPECIFIERS 0
#define NANOPRINTF_USE_BINARY_FORMAT_SPECIFIERS 0
#define NANOPRINTF_USE_WRITEBACK_FORMAT_SPECIFIERS 0
#define NANOPRINTF_USE_ALT_FORM_FLAG 0
#define NANOPRINTF_VISIBILITY_STATIC
#define NANOPRINTF_IMPLEMENTATION
#include "nanoprintf.h"

#ifndef FIRMWARE_FORMATTER_HOST_TEST
_Static_assert(sizeof(int) == 3, "MOS formatter requires a 24-bit int");
_Static_assert(sizeof(long) == 4, "MOS formatter requires a 32-bit long");
_Static_assert(sizeof(void *) == 3, "MOS formatter requires a 24-bit pointer");
_Static_assert(
    ULONG_MAX > UINTPTR_MAX,
    "nanoprintf must select long as its integer conversion accumulator");
#endif

extern int putch(int character);

static void firmware_putc(int character, void *context) {
  (void)context;
  (void)putch(character);
}

int printf(const char *format, ...) {
  va_list args;
  va_start(args, format);
  int const result = npf_vpprintf(firmware_putc, NULL, format, args);
  va_end(args);
  return result;
}

int sprintf(char *buffer, const char *format, ...) {
  va_list args;
  va_start(args, format);
  int const result = npf_vsnprintf(buffer, (size_t)INT_MAX, format, args);
  va_end(args);
  return result;
}
