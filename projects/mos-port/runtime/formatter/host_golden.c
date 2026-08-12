/* Host-side semantic smoke tests for the selected nanoprintf configuration. */

#include <stddef.h>

static char captured[32];
static size_t captured_length;

#define GOLDEN_PATTERN(pattern) ((void)sizeof(pattern))

int putch(int character) {
  if (captured_length < sizeof(captured)) {
    captured[captured_length++] = (char)character;
  }
  return character;
}

#define FIRMWARE_FORMATTER_HOST_TEST
#include "firmware_printf.c"

static int strings_equal(char const *left, char const *right) {
  while (*left && (*left == *right)) {
    ++left;
    ++right;
  }
  return *left == *right;
}

int main(void) {
  char buffer[96];

  GOLDEN_PATTERN("%*lu");
  if (sprintf(buffer, "%*lu", 10, 4294967295UL) != 10 ||
      !strings_equal(buffer, "4294967295")) {
    return 1;
  }
  GOLDEN_PATTERN("%06x");
  if (sprintf(buffer, "%06x", 0xffffffU) != 6 ||
      !strings_equal(buffer, "ffffff")) {
    return 2;
  }
  GOLDEN_PATTERN("%-*s");
  if (sprintf(buffer, "%-*s", 5, "xy") != 5 ||
      !strings_equal(buffer, "xy   ")) {
    return 3;
  }
  GOLDEN_PATTERN("%.*s");
  if (sprintf(buffer, "%.*s", 3, "abcdef") != 3 ||
      !strings_equal(buffer, "abc")) {
    return 4;
  }
  if (sprintf(buffer, "%ld", (-2147483647L - 1L)) != 11 ||
      !strings_equal(buffer, "-2147483648")) {
    return 5;
  }
  GOLDEN_PATTERN("%u");
  if (sprintf(buffer, "%u", 16777215U) != 8 ||
      !strings_equal(buffer, "16777215")) {
    return 6;
  }
  GOLDEN_PATTERN("%d");
  if (sprintf(buffer, "%d", -8388608) != 8 ||
      !strings_equal(buffer, "-8388608")) {
    return 7;
  }
  GOLDEN_PATTERN("%02X");
  if (sprintf(buffer, "%02X", 0xAU) != 2 ||
      !strings_equal(buffer, "0A")) {
    return 8;
  }

  GOLDEN_PATTERN("%%");
  if (sprintf(buffer, "%%") != 1 || !strings_equal(buffer, "%")) {
    return 10;
  }
  GOLDEN_PATTERN("%02d");
  if (sprintf(buffer, "%02d", 7) != 2 || !strings_equal(buffer, "07")) {
    return 11;
  }
  GOLDEN_PATTERN("%04d");
  if (sprintf(buffer, "%04d", -7) != 4 || !strings_equal(buffer, "-007")) {
    return 12;
  }
  GOLDEN_PATTERN("%06X");
  if (sprintf(buffer, "%06X", 0xffffffU) != 6 ||
      !strings_equal(buffer, "FFFFFF")) {
    return 13;
  }
  GOLDEN_PATTERN("%2d");
  if (sprintf(buffer, "%2d", -8) != 2 || !strings_equal(buffer, "-8")) {
    return 14;
  }
  GOLDEN_PATTERN("%4d");
  if (sprintf(buffer, "%4d", 7) != 4 || !strings_equal(buffer, "   7")) {
    return 15;
  }
  GOLDEN_PATTERN("%6d");
  if (sprintf(buffer, "%6d", -8388608) != 8 ||
      !strings_equal(buffer, "-8388608")) {
    return 16;
  }
  GOLDEN_PATTERN("%c");
  if (sprintf(buffer, "%c", 'Z') != 1 || !strings_equal(buffer, "Z")) {
    return 17;
  }
  GOLDEN_PATTERN("%s");
  if (sprintf(buffer, "%s", "") != 0 || !strings_equal(buffer, "")) {
    return 18;
  }

  captured_length = 0;
  if (printf("\n\r") != 2 || captured_length != 2 ||
      captured[0] != '\n' || captured[1] != '\r') {
    return 9;
  }
  return 0;
}
