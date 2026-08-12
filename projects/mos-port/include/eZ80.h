#ifndef MOS_AGONDEV_EZ80_COMPAT_H
#define MOS_AGONDEV_EZ80_COMPAT_H

#include <stdint.h>

#define MOS_IO(address) \
    (*((volatile uint8_t __attribute__((address_space(3))) *)(address)))

#define TMR0_CTL  MOS_IO(0x80)
#define TMR0_DR_L MOS_IO(0x81)
#define TMR0_RR_L MOS_IO(0x81)
#define TMR0_DR_H MOS_IO(0x82)
#define TMR0_RR_H MOS_IO(0x82)

#define PB_DR     MOS_IO(0x9A)
#define PB_DDR    MOS_IO(0x9B)
#define PB_ALT1   MOS_IO(0x9C)
#define PB_ALT2   MOS_IO(0x9D)
#define PC_DR     MOS_IO(0x9E)
#define PC_DDR    MOS_IO(0x9F)
#define PC_ALT1   MOS_IO(0xA0)
#define PC_ALT2   MOS_IO(0xA1)
#define PD_DR     MOS_IO(0xA2)
#define PD_DDR    MOS_IO(0xA3)
#define PD_ALT1   MOS_IO(0xA4)
#define PD_ALT2   MOS_IO(0xA5)

#define UART0_BRG_L MOS_IO(0xC0)
#define UART0_IER   MOS_IO(0xC1)
#define UART0_BRG_H MOS_IO(0xC1)
#define UART0_FCTL  MOS_IO(0xC2)
#define UART0_LCTL  MOS_IO(0xC3)
#define UART0_MCTL  MOS_IO(0xC4)

#define I2C_CTL MOS_IO(0xCB)
#define I2C_CCR MOS_IO(0xCC)

#define UART1_BRG_L MOS_IO(0xD0)
#define UART1_IER   MOS_IO(0xD1)
#define UART1_BRG_H MOS_IO(0xD1)
#define UART1_FCTL  MOS_IO(0xD2)
#define UART1_LCTL  MOS_IO(0xD3)
#define UART1_MCTL  MOS_IO(0xD4)

#define CLK_PPD1 MOS_IO(0xDB)

#define UART0_IVECT  0x18
#define UART1_IVECT  0x1A
#define I2C_IVECT    0x1C
#define PORTB1_IVECT 0x32

#define PORTC_DRVAL_DEF   0xFF
#define PORTC_DDRVAL_DEF  0xFF
#define PORTC_ALT0VAL_DEF 0xFF
#define PORTC_ALT1VAL_DEF 0x00
#define PORTC_ALT2VAL_DEF 0x00
#define PORTD_DRVAL_DEF   0xFF
#define PORTD_DDRVAL_DEF  0xFF
#define PORTD_ALT0VAL_DEF 0xFF
#define PORTD_ALT1VAL_DEF 0x00
#define PORTD_ALT2VAL_DEF 0x00

#define PORTPIN_ZERO  0x01
#define PORTPIN_ONE   0x02
#define PORTPIN_TWO   0x04
#define PORTPIN_THREE 0x08

#define DI() __asm__ volatile ("di")
#define EI() __asm__ volatile ("ei")

#endif
