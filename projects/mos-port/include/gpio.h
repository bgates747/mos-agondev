#ifndef MOS_AGONDEV_GPIO_COMPAT_H
#define MOS_AGONDEV_GPIO_COMPAT_H

#include <ez80.h>

#define SETREG(reg, bits) ((reg) |= (uint8_t)(bits))
#define RESETREG(reg, bits) ((reg) &= (uint8_t)~(uint8_t)(bits))

#endif
