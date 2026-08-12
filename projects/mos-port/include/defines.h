#ifndef MOS_AGONDEV_ZILOG_DEFINES_COMPAT_H
#define MOS_AGONDEV_ZILOG_DEFINES_COMPAT_H

#include <stdint.h>

typedef int8_t INT8;
typedef uint8_t UINT8;
typedef int16_t INT16;
typedef uint16_t UINT16;
typedef int24_t INT24;
typedef uint24_t UINT24;
typedef int32_t INT32;
typedef uint32_t UINT32;

typedef signed char CHAR;
typedef unsigned char UCHAR;
typedef uint8_t BYTE;
typedef uint16_t WORD;
typedef uint32_t DWORD;
typedef uint64_t QWORD;
typedef int24_t INT;
typedef uint24_t UINT;
typedef uint8_t BOOL;
typedef void VOID;

#ifndef FALSE
#define FALSE ((BOOL)0)
#endif
#ifndef TRUE
#define TRUE ((BOOL)1)
#endif

#endif
