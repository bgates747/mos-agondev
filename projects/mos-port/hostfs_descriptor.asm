/*
 * Fab Agon Emulator directory-backed SD descriptor.
 *
 * The emulator discovers this fixed ROM table before attempting its legacy
 * ZDS map parser.  Byte 0x6E is the format version (2); the first address
 * begins immediately at 0x6F.  Each address is little-endian 24-bit.
 */

        .assume ADL = 1
        .section .mos_descriptor,"a",@progbits

        .ascii  "MOS"
        .byte   2
        d24     _f_chdir
        d24     _f_chdrive
        d24     _f_close
        d24     _f_closedir
        d24     _f_getcwd
        d24     _f_getfree
        d24     _f_getlabel
        d24     _f_gets
        d24     _f_lseek
        d24     _f_mkdir
        d24     _f_mount
        d24     _f_open
        d24     _f_opendir
        d24     _f_printf
        d24     _f_putc
        d24     _f_puts
        d24     _f_read
        d24     _f_readdir
        d24     _f_rename
        d24     _f_setlabel
        d24     _f_stat
        d24     _f_sync
        d24     _f_truncate
        d24     _f_unlink
        d24     _f_write
