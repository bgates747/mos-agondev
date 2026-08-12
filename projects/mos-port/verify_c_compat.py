#!/usr/bin/env python3
"""Verify the allow-listed AgonDev C/header contract for the MOS port."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parent
C_SOURCES = (
    "main.c",
    "src/clock.c",
    "src/i2c.c",
    "src/mos.c",
    "src/mos_editor.c",
    "src/mos_file.c",
    "src/mos_sysvars.c",
    "src/strings.c",
    "src/tests.c",
    "src/timer.c",
    "src/uart.c",
    "src_fatfs/diskio.c",
    "src_fatfs/ff.c",
    "src_fatfs/ffsystem.c",
    "src_fatfs/ffunicode.c",
    "src_umm_malloc/umm_malloc.c",
)
COMMON_FLAGS = (
    "-target",
    "ez80-none-elf",
    "-march=ez80",
    "-mllvm",
    "-z80-gas-style",
    "-mllvm",
    "-z80-print-zero-offset",
    "-std=gnu17",
    "-Wall",
    "-Wextra",
    "-ffreestanding",
    "-fno-threadsafe-statics",
    "-Wa,-march=ez80+full",
)
REGISTER_INSTRUCTIONS = {
    0x80: "TMR0_CTL",
    0x81: "TMR0_DR_L/TMR0_RR_L",
    0x82: "TMR0_DR_H/TMR0_RR_H",
    0x9E: "PC_DR",
    0x9F: "PC_DDR",
    0xA0: "PC_ALT1",
    0xA1: "PC_ALT2",
    0xA2: "PD_DR",
    0xA3: "PD_DDR",
    0xA4: "PD_ALT1",
    0xA5: "PD_ALT2",
    0xC0: "UART0_BRG_L",
    0xC1: "UART0_IER/UART0_BRG_H",
    0xC2: "UART0_FCTL",
    0xC3: "UART0_LCTL",
    0xC4: "UART0_MCTL",
    0xCB: "I2C_CTL",
    0xCC: "I2C_CCR",
    0xD0: "UART1_BRG_L",
    0xD1: "UART1_IER/UART1_BRG_H",
    0xD2: "UART1_FCTL",
    0xD3: "UART1_LCTL",
    0xD4: "UART1_MCTL",
    0xDB: "CLK_PPD1",
}
LOCAL_HEADERS = {"defines.h", "ez80.h", "gpio.h"}


class ContractError(RuntimeError):
    pass


def run(command: Sequence[str | Path], *, cwd: Path = ROOT) -> str:
    completed = subprocess.run(
        [str(item) for item in command],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ContractError(f"command failed ({' '.join(map(str, command))}): {detail}")
    return completed.stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_headers(contract: dict[str, object], toolchain: Path) -> None:
    expected_commit = contract["agondev_commit"]
    actual_commit = run(["git", "-C", toolchain.parent, "rev-parse", "HEAD"]).strip()
    if actual_commit != expected_commit:
        raise ContractError(
            f"AgonDev source commit changed: expected {expected_commit}, "
            f"found {actual_commit}"
        )
    official = contract["official_headers"]
    assert isinstance(official, dict)
    include = toolchain / "include"
    found = {path.name for path in include.iterdir() if path.is_file()}
    missing = sorted(set(official) - found)
    if missing:
        raise ContractError("missing official AgonDev headers: " + ", ".join(missing))
    for name, expected in official.items():
        actual = sha256(include / name)
        if actual != expected:
            raise ContractError(
                f"official AgonDev header changed: {name} "
                f"(expected {expected}, found {actual})"
            )

    local_headers = {
        path.name for path in (ROOT / "include").iterdir() if path.is_file()
    }
    if local_headers != LOCAL_HEADERS:
        raise ContractError(
            "local compatibility header set changed: "
            f"expected {sorted(LOCAL_HEADERS)}, found {sorted(local_headers)}"
        )

    registers = contract["registers"]
    constants = contract["hardware_constants"]
    assert isinstance(registers, dict)
    assert isinstance(constants, dict)
    official_text = (include / "ez80f92.h").read_text(encoding="utf-8")
    official_registers = {
        match.group(1): int(match.group(2), 0)
        for match in re.finditer(
            r"^#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(0[xX][0-9A-Fa-f]+|[0-9]+)\s*$",
            official_text,
            re.MULTILINE,
        )
    }
    for name, expected in {**registers, **constants}.items():
        actual = official_registers.get(name)
        if actual != expected:
            raise ContractError(
                f"official AgonDev register changed: {name} "
                f"(expected 0x{expected:02x}, found {actual!r})"
            )

    facade_text = (ROOT / "include/ez80.h").read_text(encoding="utf-8")
    facade_names = set(re.findall(r"MOS_AGONDEV_ADDR_([A-Za-z0-9_]+)\s*=", facade_text))
    if facade_names != set(registers):
        raise ContractError(
            "hardware facade allow-list differs from contract: "
            f"expected {sorted(registers)}, found {sorted(facade_names)}"
        )


def dependency_headers(clang: Path, toolchain: Path, worktree: Path) -> set[str]:
    include = toolchain / "include"
    command_base = [
        clang,
        "-Iinclude",
        f"-I{worktree / 'src'}",
        f"-I{worktree / 'src_fatfs'}",
        f"-I{worktree / 'src_startup'}",
        f"-I{worktree / 'src_umm_malloc'}",
        "-nostdinc",
        "-isystem",
        include,
        "-DAGONDEV",
        "-D_EZ80",
        "-D_EZ80F92",
        "-DNDEBUG",
        "-target",
        "ez80-none-elf",
        "-march=ez80",
        "-std=gnu17",
        "-ffreestanding",
        "-M",
        "-MT",
        "probe",
    ]
    dependencies: set[str] = set()
    include_prefix = include.resolve()
    for relative in C_SOURCES:
        output = run([*command_base, worktree / relative])
        for token in output.replace("\\\n", " ").split()[1:]:
            path = Path(token)
            try:
                name = path.resolve().relative_to(include_prefix).as_posix()
            except (FileNotFoundError, ValueError):
                continue
            dependencies.add(name)
    return dependencies


def verify_dependencies(
    contract: dict[str, object], clang: Path, toolchain: Path, worktree: Path
) -> None:
    expected = set(contract["source_headers"])
    actual = dependency_headers(clang, toolchain, worktree)
    if actual != expected:
        raise ContractError(
            "official header dependency set changed: "
            f"expected {sorted(expected)}, found {sorted(actual)}"
        )


def compile_contract_probe(clang: Path, toolchain: Path, output: Path) -> None:
    run(
        [
            clang,
            "-Iinclude",
            "-nostdinc",
            "-isystem",
            toolchain / "include",
            "-DAGONDEV",
            "-D_EZ80",
            "-D_EZ80F92",
            *COMMON_FLAGS,
            "-Werror",
            "-Oz",
            "-c",
            "c_compat/contract_probe.c",
            "-o",
            output,
        ]
    )


def compile_type_probe(clang: Path, toolchain: Path, source: Path, output: Path,
                       type_sizes: dict[str, int]) -> None:
    lines = ["#include <defines.h>"]
    lines.extend(
        f'_Static_assert(sizeof({name}) == {size}, "{name} size changed");'
        for name, size in sorted(type_sizes.items())
    )
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run([
        clang, "-Iinclude", "-nostdinc", "-isystem", toolchain / "include",
        "-DAGONDEV", *COMMON_FLAGS, "-Werror", "-Oz", "-c", source, "-o", output,
    ])


def verify_probe_disassembly(objdump: Path, object_file: Path) -> None:
    disassembly = run([objdump, "-dr", object_file])
    found = {int(match.group(1), 16) for match in re.finditer(
        r"\b(?:in0|out0)\s+(?:[a-z]+,)?\(0x([0-9a-f]{2})\)", disassembly
    )}
    expected = {0x80, 0x81, 0x82, 0xA0, 0xA3, 0xC1, 0xCB, 0xCC, 0xD1, 0xDB}
    if found != expected:
        names = lambda values: [REGISTER_INSTRUCTIONS[value] for value in sorted(values)]
        raise ContractError(
            "hardware probe I/O instructions changed: "
            f"missing {names(expected - found)}, extra {names(found - expected)}"
        )


def symbol_body(disassembly: str, symbol: str) -> str:
    match = re.search(rf"^[0-9a-f]+ <{re.escape(symbol)}>:\n(.*?)(?=\n\n|\Z)",
                      disassembly, re.MULTILINE | re.DOTALL)
    if not match:
        raise ContractError(f"object is missing {symbol}")
    return match.group(1)


def verify_quickrand(objdump: Path, main_object: Path) -> None:
    body = symbol_body(run([objdump, "-dr", main_object]), "_quickrand")
    instructions = [
        match.group(1).strip()
        for line in body.splitlines()
        if (match := re.match(r"\s*[0-9a-f]+:\s+(?:[0-9a-f]{2}\s+)+(.+)$", line))
    ]
    if not instructions or instructions[0] != "ld a,r" or instructions[-1] != "ret":
        raise ContractError(f"quickrand instruction boundary changed: {instructions}")
    expected = ["ld a,r", "or a,a", "sbc hl,hl", "ld l,a", "ret"]
    if instructions != expected:
        raise ContractError(
            "quickrand no longer zero-extends the A result through HLU: "
            f"expected {expected}, found {instructions}"
        )
    if any("call" in item or "ld hl,0x0000" in item for item in instructions):
        raise ContractError(f"quickrand contains unexpected synthesized work: {instructions}")


def verify_disk_timestamp(objdump: Path, disk_object: Path) -> None:
    body = symbol_body(run([objdump, "-dr", disk_object]), "_get_fattime")
    if "__lshl" not in body or not re.search(r"\bld l,0x19\b", body):
        raise ContractError("get_fattime no longer performs its year shift as 32-bit << 25")


def verify_source_rules(worktree: Path) -> None:
    texts = {
        relative: (worktree / relative).read_text(encoding="utf-8", errors="strict")
        for relative in C_SOURCES
    }
    all_sources = [
        path.read_text(encoding="utf-8", errors="strict")
        for path in sorted(worktree.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".c", ".h"}
    ]
    joined = "\n".join(all_sources)
    for spelling in ("<eZ80.h>", "<CTYPE.h>", "<String.h>"):
        if spelling in joined:
            raise ContractError(f"non-portable include spelling remains: {spelling}")
    if re.search(r"extern\s+void\s+\w+\s*\[\s*\]", joined):
        raise ContractError("invalid void array declaration remains in prepared C source")
    main = texts["main.c"]
    if '__asm__ volatile ("ld a,r" : "=a"(value) : : "cc");' not in main:
        raise ContractError("quickrand explicit A-register output constraint is missing")
    diskio = texts["src_fatfs/diskio.c"]
    if "(DWORD)(tstruct.year - EPOCH_YEAR) << 25" not in diskio:
        raise ContractError("disk timestamp shift lacks its pre-shift DWORD cast")


def source_hardware_names(worktree: Path, official_header: Path) -> set[str]:
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="strict")
        for path in sorted(worktree.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".c", ".h"}
    )
    text = re.sub(
        r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
        " ",
        text,
        flags=re.DOTALL,
    )
    source_names = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text))
    official_names = set(re.findall(
        r"^#define\s+([A-Za-z_][A-Za-z0-9_]*)\b",
        official_header.read_text(encoding="utf-8"),
        re.MULTILINE,
    ))
    return source_names & official_names


def verify_hardware_allow_list(contract: dict[str, object], toolchain: Path,
                               worktree: Path) -> None:
    registers = contract["registers"]
    constants = contract["hardware_constants"]
    assert isinstance(registers, dict) and isinstance(constants, dict)
    expected = set(registers) | set(constants)
    actual = source_hardware_names(worktree, toolchain / "include/ez80f92.h")
    if actual != expected:
        raise ContractError(
            "MOS official hardware dependency set changed: "
            f"expected {sorted(expected)}, found {sorted(actual)}"
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, default=ROOT.parents[1] / "toolchains/agondev")
    parser.add_argument("--worktree", type=Path, default=ROOT / "worktree")
    parser.add_argument("--object-dir", type=Path, default=ROOT / "obj")
    parser.add_argument("--contract", type=Path, default=ROOT / "c_compat_contract.json")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
        toolchain = args.toolchain.resolve(strict=True)
        worktree = args.worktree.resolve(strict=True)
        object_dir = args.object_dir.resolve(strict=True)
        clang = toolchain / "bin/ez80-none-elf-clang"
        objdump = toolchain / "bin/ez80-none-elf-objdump"
        verify_headers(contract, toolchain)
        verify_dependencies(contract, clang, toolchain, worktree)
        verify_source_rules(worktree)
        verify_hardware_allow_list(contract, toolchain, worktree)
        with tempfile.TemporaryDirectory(prefix="mos-agondev-c-contract-") as temporary:
            temporary_path = Path(temporary)
            probe = temporary_path / "contract_probe.o"
            compile_contract_probe(clang, toolchain, probe)
            verify_probe_disassembly(objdump, probe)
            type_sizes = contract["type_sizes"]
            assert isinstance(type_sizes, dict)
            compile_type_probe(
                clang,
                toolchain,
                temporary_path / "type_probe.c",
                temporary_path / "type_probe.o",
                type_sizes,
            )
        verify_quickrand(objdump, object_dir / "main.o")
        verify_disk_timestamp(objdump, object_dir / "src_fatfs/diskio.o")
    except (ContractError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"C compatibility verified: {len(C_SOURCES)} units, "
        f"{len(contract['source_headers'])} official headers, "
        f"{len(contract['registers']) + len(contract['hardware_constants'])} "
        "allow-listed hardware names"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
