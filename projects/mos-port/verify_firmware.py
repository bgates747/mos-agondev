#!/usr/bin/env python3
"""Verify a fully linked AgonDev MOS firmware image and Fab descriptor."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


ROM_LIMIT = 0x020000
DESCRIPTOR_ADDRESS = 0x6B
DESCRIPTOR_VERSION = 2
DESCRIPTOR_SYMBOLS = (
    "_f_chdir", "_f_chdrive", "_f_close", "_f_closedir", "_f_getcwd",
    "_f_getfree", "_f_getlabel", "_f_gets", "_f_lseek", "_f_mkdir",
    "_f_mount", "_f_open", "_f_opendir", "_f_printf", "_f_putc",
    "_f_puts", "_f_read", "_f_readdir", "_f_rename", "_f_setlabel",
    "_f_stat", "_f_sync", "_f_truncate", "_f_unlink", "_f_write",
)


def run(*arguments: Path | str) -> str:
    completed = subprocess.run(
        [str(value) for value in arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout


def symbols(nm: Path, elf: Path) -> tuple[dict[str, int], list[str]]:
    output = run(nm, "-P", elf)
    definitions: dict[str, int] = {}
    undefined: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        if fields[1].upper() == "U":
            undefined.append(fields[0])
        elif len(fields) >= 3:
            definitions[fields[0]] = int(fields[2], 16)
    return definitions, undefined


def sections(readelf: Path, elf: Path) -> dict[str, tuple[str, int, int]]:
    output = run(readelf, "-SW", elf)
    result: dict[str, tuple[str, int, int]] = {}
    pattern = re.compile(
        r"^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+"
        r"[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+"
    )
    for line in output.splitlines():
        match = pattern.match(line)
        if match:
            name, kind, address, size = match.groups()
            result[name] = (kind, int(address, 16), int(size, 16))
    return result


def decode24(data: bytes) -> int:
    return data[0] | data[1] << 8 | data[2] << 16


def verify(elf: Path, binary: Path, nm: Path, readelf: Path) -> None:
    definitions, undefined = symbols(nm, elf)
    if undefined:
        raise ValueError(f"linked ELF retains undefined symbols: {sorted(undefined)}")

    required = {
        "_reset": 0,
        "__vector_table": 0x100,
        "__1st_jump_table": 0x160,
        "__startup_start": 0x220,
        "__stack": 0x0C0000,
    }
    for name, expected in required.items():
        actual = definitions.get(name)
        if actual != expected:
            raise ValueError(f"{name}: expected 0x{expected:06X}, got {actual!r}")

    table = sections(readelf, elf)
    exact_sections = {
        ".reset": ("PROGBITS", 0x000000, 0x6B),
        ".reset_fill": ("PROGBITS", 0x00006B, 0x95),
        ".ivecs": ("PROGBITS", 0x000100, 0x120),
        ".startup": ("PROGBITS", 0x000220, table.get(".startup", ("", 0, 0))[2]),
        ".data": ("PROGBITS", 0x0BC000, table.get(".data", ("", 0, 0))[2]),
        ".bss": ("NOBITS", table.get(".bss", ("", 0, 0))[1], table.get(".bss", ("", 0, 0))[2]),
        ".ivjmptbl": ("NOBITS", table.get(".ivjmptbl", ("", 0, 0))[1], 0xC0),
    }
    for name, expected in exact_sections.items():
        if table.get(name) != expected:
            raise ValueError(f"{name}: expected {expected}, got {table.get(name)}")

    image = binary.read_bytes()
    rom_end = definitions.get("__rom_image_end")
    if not isinstance(rom_end, int) or len(image) != rom_end:
        raise ValueError(f"binary length {len(image)} does not equal __rom_image_end {rom_end!r}")
    if len(image) > ROM_LIMIT:
        raise ValueError(f"firmware image exceeds 128 KiB: {len(image)} bytes")

    descriptor = image[DESCRIPTOR_ADDRESS:0xBA]
    if descriptor[:3] != b"MOS" or descriptor[3] != DESCRIPTOR_VERSION:
        raise ValueError("Fab MOS descriptor version 2 is absent at 0x6B")
    addresses = [decode24(descriptor[offset:offset + 3]) for offset in range(4, 0x4F, 3)]
    expected_addresses = []
    for name in DESCRIPTOR_SYMBOLS:
        if name not in definitions:
            raise ValueError(f"descriptor symbol is missing from ELF: {name}")
        expected_addresses.append(definitions[name])
    if addresses != expected_addresses:
        raise ValueError("Fab descriptor addresses do not match linked FatFS symbols")
    if image[0xBA:0x100] != b"\xFF" * (0x100 - 0xBA):
        raise ValueError("unused reset-page bytes are not 0xFF")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--toolbin", type=Path, required=True)
    args = parser.parse_args()
    verify(
        args.elf,
        args.binary,
        args.toolbin / "ez80-none-elf-nm",
        args.toolbin / "ez80-none-elf-readelf",
    )
    print(f"MOS firmware verified: {args.binary.stat().st_size} bytes, Fab hostfs descriptor valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
