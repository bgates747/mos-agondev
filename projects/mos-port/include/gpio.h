#ifndef MOS_AGONDEV_GPIO_COMPAT_H
#define MOS_AGONDEV_GPIO_COMPAT_H

#include <eZ80.h>

#define SETREG(reg, bits) ((reg) |= (bits))
#define RESETREG(reg, bits) ((reg) &= (uint8_t)~(bits))

#endif
