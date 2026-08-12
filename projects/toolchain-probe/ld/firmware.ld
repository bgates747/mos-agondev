ENTRY(_reset)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x000000, LENGTH = 0x020000
    RAM   (rwx) : ORIGIN = 0x0BC000, LENGTH = 0x004000
}

SECTIONS
{
    .reset 0x000000 :
    {
        KEEP(*(.reset))
    } > FLASH

    .vectors 0x000100 :
    {
        KEEP(*(.vectors))
    } > FLASH

    .text 0x000220 :
    {
        *(.startup)
        *(.text .text.*)
        *(.rodata .rodata.*)
    } > FLASH

    .data : AT(LOADADDR(.text) + SIZEOF(.text))
    {
        __low_data = .;
        *(.data .data.*)
        __data_end = .;
    } > RAM
    __low_romdata = LOADADDR(.data);
    __len_data = SIZEOF(.data);

    .bss (NOLOAD) :
    {
        __low_bss = .;
        *(.bss .bss.* COMMON)
        __bss_end = .;
    } > RAM
    __len_bss = SIZEOF(.bss);

    .ivjmptbl (NOLOAD) :
    {
        *(.ivjmptbl)
    } > RAM

    __stack = ORIGIN(RAM) + LENGTH(RAM);
    __heaptop = __stack - 1;
    __heapbot = ADDR(.bss) + SIZEOF(.bss);
    __rom_image_end = LOADADDR(.data) + SIZEOF(.data);

    /DISCARD/ :
    {
        *(.comment)
        *(.note*)
    }
}

ASSERT(__rom_image_end <= ORIGIN(FLASH) + LENGTH(FLASH),
       "firmware image exceeds the 128 KiB flash window")
ASSERT(__heapbot <= __stack,
       "static RAM sections exceed the 16 KiB internal RAM window")
