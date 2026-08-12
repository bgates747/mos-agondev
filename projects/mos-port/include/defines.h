#ifndef MOS_AGONDEV_ZILOG_DEFINES_COMPAT_H
#define MOS_AGONDEV_ZILOG_DEFINES_COMPAT_H

#include <stdint.h>

/*
 * ZDS's <defines.h> is not part of AgonDev.  Keep the compatibility surface
 * deliberately limited to aliases used by agon-mos, and derive every alias
 * from AgonDev's compiler-owned fixed-width types.
 */
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

_Static_assert(sizeof(INT8) == 1 && sizeof(UINT8) == 1,
               "ZDS 8-bit aliases changed");
_Static_assert(sizeof(INT16) == 2 && sizeof(UINT16) == 2,
               "ZDS 16-bit aliases changed");
_Static_assert(sizeof(INT24) == 3 && sizeof(UINT24) == 3,
               "ZDS 24-bit aliases changed");
_Static_assert(sizeof(INT32) == 4 && sizeof(UINT32) == 4,
               "ZDS 32-bit aliases changed");
_Static_assert(sizeof(QWORD) == 8, "ZDS QWORD alias changed");
_Static_assert(sizeof(INT) == 3 && sizeof(UINT) == 3,
               "ZDS native integer aliases changed");
_Static_assert(sizeof(BOOL) == 1, "ZDS BOOL alias changed");
_Static_assert((CHAR)-1 < 0 && (INT)-1 < 0 && (INT8)-1 < 0 &&
                   (INT16)-1 < 0 && (INT24)-1 < 0 && (INT32)-1 < 0,
               "signed ZDS aliases changed signedness");
_Static_assert((UCHAR)-1 > 0 && (BYTE)-1 > 0 && (WORD)-1 > 0 &&
                   (DWORD)-1 > 0 && (QWORD)-1 > 0 && (UINT)-1 > 0 &&
                   (UINT8)-1 > 0 && (UINT16)-1 > 0 && (UINT24)-1 > 0 &&
                   (UINT32)-1 > 0,
               "unsigned ZDS aliases changed signedness");

#ifndef FALSE
#define FALSE ((BOOL)0)
#endif
#ifndef TRUE
#define TRUE ((BOOL)1)
#endif

#endif
