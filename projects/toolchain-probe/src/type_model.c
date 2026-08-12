#include <limits.h>
#include <stddef.h>
#include <stdint.h>

_Static_assert(CHAR_BIT == 8, "AgonDev must use 8-bit bytes");
_Static_assert(sizeof(short) == 2, "AgonDev short must be 16-bit");
_Static_assert(sizeof(int) == 3, "AgonDev int must be 24-bit");
_Static_assert(sizeof(long) == 4, "AgonDev long must be 32-bit");
_Static_assert(sizeof(void *) == 3, "AgonDev pointers must be 24-bit");
_Static_assert(sizeof(float) == 4, "AgonDev float must be 32-bit");
_Static_assert(sizeof(double) == 4, "AgonDev double must be 32-bit");
_Static_assert(sizeof(size_t) == 3, "AgonDev size_t must be 24-bit");

volatile uint8_t probe_bss;
volatile uint8_t probe_data = 0x5a;

/* The disassembly of this function is an ABI probe: arguments occupy
   three-byte stack slots and an eight-bit return value is returned in A. */
uint8_t probe_abi(uint24_t value, const uint8_t *bytes, uint16_t count)
{
    return (uint8_t)(value + bytes[0] + count);
}
