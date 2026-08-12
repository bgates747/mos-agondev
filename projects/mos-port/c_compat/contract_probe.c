#include <defines.h>
#include <ez80.h>
#include <gpio.h>

void mos_contract_timer_probe(void)
{
    TMR0_CTL = 0;
    TMR0_RR_L = 0x34;
    TMR0_RR_H = 0x12;
}

void mos_contract_uart_probe(void)
{
    UART0_IER = 0;
    UART1_IER = 0;
    SETREG(PD_DDR, PORTPIN_ZERO);
    RESETREG(PC_ALT1, PORTPIN_THREE);
}

void mos_contract_i2c_probe(void)
{
    CLK_PPD1 = 0;
    I2C_CTL = 0;
    I2C_CCR = 0;
}
