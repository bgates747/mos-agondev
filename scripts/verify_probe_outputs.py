#!/usr/bin/env python3
"""Verify the measured firmware-layout and all-C probe outputs."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOLCHAIN = ROOT / "toolchains/agondev"
FIRMWARE_ROOT = ROOT / "projects/toolchain-probe"
C_PROBE_ROOT = ROOT / "projects/mos-port"

EXPECTED_FIRMWARE_SECTIONS = {
    ".reset": (0x000009, 0x000000, 0x000000),
    ".vectors": (0x000120, 0x000100, 0x000100),
    ".text": (0x000042, 0x000220, 0x000220),
    ".data": (0x000001, 0x0BC000, 0x000262),
    ".bss": (0x000001, 0x0BC001, 0x000263),
}


def run(*arguments: str | Path) -> str:
    return subprocess.run(
        [str(argument) for argument in arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_objdump_sections(output: str) -> dict[str, tuple[int, int, int]]:
    sections: dict[str, tuple[int, int, int]] = {}
    pattern = re.compile(
        r"^\s*\d+\s+(\.\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s",
        re.IGNORECASE | re.MULTILINE,
    )
    for name, size, vma, lma in pattern.findall(output):
        sections[name] = (int(size, 16), int(vma, 16), int(lma, 16))
    return sections


def parse_size_totals(output: str) -> dict[str, int]:
    totals = {name: 0 for name in (".text", ".rodata", ".data", ".bss")}
    pattern = re.compile(r"^\s*(\.\S+)\s+(\d+)\s+\d+\s*$", re.MULTILINE)
    for name, size in pattern.findall(output):
        if name in totals:
            totals[name] += int(size)
    return totals


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    baseline = json.loads((ROOT / "evidence/baseline.json").read_text(encoding="utf-8"))
    toolbin = TOOLCHAIN / "bin"
    elf = FIRMWARE_ROOT / "bin/firmware_probe.elf"
    binary = FIRMWARE_ROOT / "bin/firmware_probe.bin"
    require(elf.is_file() and binary.is_file(), "Build the firmware probe first")

    sections = parse_objdump_sections(
        run(toolbin / "ez80-none-elf-objdump", "-h", elf)
    )
    require(
        sections == EXPECTED_FIRMWARE_SECTIONS,
        f"Unexpected firmware section layout: {sections}",
    )
    file_header = run(toolbin / "ez80-none-elf-objdump", "-f", elf)
    require("architecture: ez80-adl" in file_header, "Firmware ELF is not eZ80 ADL")
    require("start address 0x00000000" in file_header, "Firmware entry is not reset")
    require(
        not run(toolbin / "ez80-none-elf-nm", "-u", elf).strip(),
        "Firmware probe has undefined symbols",
    )
    expected_hash = baseline["measured_probes"]["firmware_probe_sha256"]
    require(sha256(binary) == expected_hash, "Firmware probe hash changed")
    require(binary.stat().st_size == 611, "Firmware probe flat-binary extent changed")

    objects = sorted((C_PROBE_ROOT / "obj").rglob("*.o"))
    expected_count = baseline["measured_probes"]["agondev_c_translation_units"]
    require(
        len(objects) == expected_count,
        f"Expected {expected_count} C objects, got {len(objects)}",
    )
    totals = parse_size_totals(run(toolbin / "ez80-none-elf-size", "-A", *objects))
    loadable = totals[".text"] + totals[".rodata"] + totals[".data"]
    expected_loadable = baseline["measured_probes"][
        "agondev_c_loadable_bytes_before_runtime_and_assembly"
    ]
    require(loadable == expected_loadable, f"C loadable size changed: {loadable}")
    require(totals[".bss"] == 1726, f"C BSS size changed: {totals['.bss']}")

    print("Firmware probe: eZ80 ADL, entry/layout/symbols/hash verified")
    print(
        f"C probe:        {len(objects)} objects, {loadable} loadable bytes, "
        f"{totals['.bss']} BSS bytes"
    )


if __name__ == "__main__":
    main()
