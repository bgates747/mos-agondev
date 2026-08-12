#include <stdint.h>

extern void slot_u8_ptr_u24(uint8_t first, char *second, uint24_t third);
extern void slot_u8_u32(uint8_t first, uint32_t second);

void call_slot_u8_ptr_u24(void) {
    slot_u8_ptr_u24(0x12, (char *)0x345678, 0xabcdef);
}

void call_slot_u8_u32(void) {
    slot_u8_u32(0x34, 0x89abcdefUL);
}
