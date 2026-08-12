#!/usr/bin/env python3
"""Build and inspect synthetic objects against the production MOS script."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path


LD_DIR = Path(__file__).resolve().parent
ROOT = LD_DIR.parents[2]
TOOLBIN = ROOT / "toolchains" / "agondev" / "bin"
FIXTURES = LD_DIR / "fixtures"

AS = TOOLBIN / "ez80-none-elf-as"
LD = TOOLBIN / "ez80-none-elf-ld"
NM = TOOLBIN / "ez80-none-elf-nm"
OBJCOPY = TOOLBIN / "ez80-none-elf-objcopy"
READELF = TOOLBIN / "ez80-none-elf-readelf"

DATA_BYTES = bytes((0xA5, 0x5A, 0x11, 0x22, 0x33))

EXPECTED_SYMBOLS = {
    "_reset": 0x000000,
    "__mos_descriptor_start": 0x00006B,
    "__mos_descriptor_end": 0x0000BA,
    "__vector_table": 0x000100,
    "__1st_jump_table": 0x000160,
    "__startup_start": 0x000220,
    "__low_code": 0x000222,
    "__low_romcode": 0x000222,
    "__len_code": 1,
    "__rom_ro_end": 0x000226,
    "__low_data": 0x0BC000,
    "__low_romdata": 0x000226,
    "__len_data": len(DATA_BYTES),
    "__rom_image_end": 0x00022B,
    "__low_bss": 0x0BC005,
    "__len_bss": 7,
    "__ivjmptbl_start": 0x0BC00C,
    "__2nd_jump_table": 0x0BC00C,
    "__ivjmptbl_end": 0x0BC0CC,
    "__heapbot": 0x0BC0CC,
    "__heaptop": 0x0BFFFF,
    "__stack_reserve": 0x0800,
    "__stack_bottom": 0x0BF800,
    "__heap_limit": 0x0BF800,
    "__stack": 0x0C0000,
    "__CS0_LBR_INIT_PARAM": 0x04,
    "__CS0_UBR_INIT_PARAM": 0x0B,
    "__CS0_CTL_INIT_PARAM": 0x08,
    "__CS0_BMC_INIT_PARAM": 0x01,
    "__CS1_LBR_INIT_PARAM": 0xC0,
    "__CS1_UBR_INIT_PARAM": 0xC7,
    "__CS1_CTL_INIT_PARAM": 0x08,
    "__CS1_BMC_INIT_PARAM": 0x00,
    "__CS2_LBR_INIT_PARAM": 0x80,
    "__CS2_UBR_INIT_PARAM": 0xBF,
    "__CS2_CTL_INIT_PARAM": 0x08,
    "__CS2_BMC_INIT_PARAM": 0x00,
    "__CS3_LBR_INIT_PARAM": 0x03,
    "__CS3_UBR_INIT_PARAM": 0x03,
    "__CS3_CTL_INIT_PARAM": 0x18,
    "__CS3_BMC_INIT_PARAM": 0x82,
    "__RAM_CTL_INIT_PARAM": 0x80,
    "__RAM_ADDR_U_INIT_PARAM": 0xB7,
    "__FLASH_CTL_INIT_PARAM": 0x28,
    "__FLASH_ADDR_U_INIT_PARAM": 0x00,
    "_SYS_CLK_FREQ": 18_432_000,
    "__copy_code_to_ram": 0,
    "__crtl": 1,
    "__low_rom": 0,
}


def run(*args: Path | str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run one tool with stable, captured diagnostics."""

    return subprocess.run(
        [str(arg) for arg in args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def require_tools() -> None:
    missing = [path for path in (AS, LD, NM, OBJCOPY, READELF) if not path.is_file()]
    if missing:
        names = ", ".join(str(path) for path in missing)
        raise SystemExit(f"missing AgonDev tools: {names}; run scripts/setup_local.py")


def assemble(source: Path, output: Path) -> None:
    run(AS, "-march=ez80+full+adl", "-o", output, source)


def link(output: Path, objects: list[Path]) -> subprocess.CompletedProcess[str]:
    return run(
        LD,
        "--orphan-handling=error",
        "-T",
        LD_DIR / "mos.ld",
        "-Map",
        output.with_suffix(".map"),
        "-o",
        output,
        *objects,
        check=False,
    )


def read_symbols(elf: Path) -> dict[str, int]:
    result = run(NM, "--format=posix", "--defined-only", elf)
    symbols: dict[str, int] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3:
            symbols[fields[0]] = int(fields[2], 16)
    return symbols


def verify_sections(elf: Path) -> None:
    output = run(READELF, "-SW", elf).stdout
    sections: dict[str, tuple[str, int, int]] = {}
    pattern = re.compile(
        r"^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+"
        r"[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+"
    )
    for line in output.splitlines():
        match = pattern.match(line)
        if match:
            name, kind, address, size = match.groups()
            sections[name] = (kind, int(address, 16), int(size, 16))

    expected = {
        ".reset": ("PROGBITS", 0x000000, 0x6B),
        ".reset_fill": ("PROGBITS", 0x00006B, 0x95),
        ".ivecs": ("PROGBITS", 0x000100, 0x120),
        ".startup": ("PROGBITS", 0x000220, 2),
        ".text": ("PROGBITS", 0x000222, 1),
        ".rodata": ("PROGBITS", 0x000223, 3),
        ".data": ("PROGBITS", 0x0BC000, len(DATA_BYTES)),
        ".bss": ("NOBITS", 0x0BC005, 7),
        ".ivjmptbl": ("NOBITS", 0x0BC00C, 0xC0),
    }
    for name, wanted in expected.items():
        actual = sections.get(name)
        if actual != wanted:
            raise AssertionError(f"{name}: expected {wanted}, got {actual}")


def verify_success(work: Path, layout_object: Path) -> None:
    elf = work / "layout.elf"
    result = link(elf, [layout_object])
    if result.returncode:
        raise AssertionError(f"valid fixture did not link:\n{result.stdout}")

    symbols = read_symbols(elf)
    for name, wanted in EXPECTED_SYMBOLS.items():
        actual = symbols.get(name)
        if actual != wanted:
            raise AssertionError(f"{name}: expected 0x{wanted:06x}, got {actual!r}")

    rom_data = symbols["__low_romdata"]
    rom_end = symbols["__rom_image_end"]
    if rom_end != rom_data + len(DATA_BYTES):
        raise AssertionError("ROM image end does not include the data load image")

    binary = work / "layout.bin"
    run(OBJCOPY, "-O", "binary", elf, binary)
    image = binary.read_bytes()
    if len(image) != rom_end:
        raise AssertionError(f"binary length 0x{len(image):x} != ROM end 0x{rom_end:x}")
    if image[rom_data:rom_end] != DATA_BYTES:
        raise AssertionError("initialized-data bytes are absent from the ROM load image")
    if image[0x6B:0x6F] != b"MOS\x02":
        raise AssertionError("Fab MOS descriptor signature is not fixed at 0x6B")
    if image[0xBA:0x100] != b"\xFF" * (0x100 - 0xBA):
        raise AssertionError("unused reset-page bytes are not erased-flash 0xFF")

    verify_sections(elf)


def verify_failure(
    work: Path,
    layout_object: Path,
    fixture_name: str,
    diagnostic: str,
) -> None:
    extra_object = work / f"{fixture_name}.o"
    assemble(FIXTURES / f"{fixture_name}.asm", extra_object)
    result = link(work / f"{fixture_name}.elf", [layout_object, extra_object])
    if result.returncode == 0:
        raise AssertionError(f"{fixture_name}: invalid layout linked successfully")
    if diagnostic not in result.stdout:
        raise AssertionError(
            f"{fixture_name}: expected diagnostic {diagnostic!r}, got:\n{result.stdout}"
        )


def main() -> int:
    require_tools()
    with tempfile.TemporaryDirectory(prefix="mos-linker-") as temporary:
        work = Path(temporary)
        layout_object = work / "layout.o"
        assemble(FIXTURES / "layout.asm", layout_object)
        verify_success(work, layout_object)
        verify_failure(
            work,
            layout_object,
            "reset_overlap",
            "reset section overlaps the optional descriptor slot at 0x6B",
        )
        verify_failure(
            work,
            layout_object,
            "bad_vectors",
            "interrupt vectors and first jump table must occupy exactly 0x120 bytes",
        )
        verify_failure(
            work,
            layout_object,
            "rom_overflow",
            "MOS firmware image exceeds the 128 KiB flash window",
        )
        verify_failure(
            work,
            layout_object,
            "stack_overlap",
            "MOS static sections consume the reserved 2 KiB stack",
        )
        verify_failure(
            work,
            layout_object,
            "ram_overflow",
            "MOS static sections exceed the 16 KiB internal RAM window",
        )

    print("MOS linker contract: valid layout and five rejection cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
