#include <ez80f92.h>
#include <stdint.h>

extern volatile uint8_t probe_bss;
extern volatile uint8_t probe_data;

void probe_main(void)
{
    __asm__ volatile ("di");
    IO(UART0_IER) = 0;
    probe_bss = IO(UART0_IIR);
    probe_data ^= probe_bss;

    for (;;) {
        __asm__ volatile ("halt");
    }
}
