#!/usr/bin/env python3
"""Audit pinned AgonDev libmos wrappers against the eZ80 Clang stack ABI."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


CONTRACT_WRAPPERS = {
    "mos_pmatch.src": "aligned frame slots",
    "mos_getleafname.src": "single stack-exchange argument",
    "mos_getargument.src": "aligned frame slots",
    "mos_extractstring.src": "aligned frame slots",
    "mos_extractnumber.src": "aligned frame slots",
    "mos_escapestring.src": "aligned frame slots",
    "mos_getError.src": "defect: mixed-width packed offsets",
    "mos_getabsolutepath.src": "delegated C-ABI tail call",
    "mos_getdirforpath.src": "delegated C-ABI tail call",
    "mos_isdirectory.src": "single stack-exchange argument",
    "mos_getrtc.src": "single stack-exchange argument",
    "mos_getsysvar_time.src": "no arguments",
    "mos_gstrans.src": "delegated C-ABI tail call",
    "mos_gsinit.src": "aligned frame slots",
    "mos_gsread.src": "aligned frame slots",
    "mos_substituteargs.src": "delegated C-ABI tail call",
    "mos_resolvepath.src": "delegated C-ABI tail call",
    "mos_fopen.src": "aligned frame slots",
    "mos_fread.src": "aligned frame slots",
    "mos_getfil.src": "single stack-exchange argument",
    "mos_feof.src": "single stack-exchange argument",
    "mos_flseek_p.src": "defect: uint32 pointer uses upper slot",
    "mos_fgetc.src": "single stack-exchange argument",
    "mos_fclose.src": "single stack-exchange argument",
    "ffs_fopen.src": "aligned frame slots",
    "ffs_fsize.src": "aligned frame slots",
    "ffs_flseek.src": "aligned split uint32 slot",
    "ffs_ftell.src": "aligned frame slots",
    "ffs_fread.src": "aligned frame slots",
    "ffs_fgets.src": "aligned frame slots",
    "ffs_ferror.src": "single stack-exchange argument",
    "ffs_flseek_p.src": "aligned frame slots",
    "ffs_feof.src": "single stack-exchange argument",
    "ffs_fclose.src": "single stack-exchange argument",
    "ffs_dopen.src": "aligned frame slots",
    "ffs_dread.src": "aligned frame slots",
    "ffs_dclose.src": "single stack-exchange argument",
    "ffs_dfindfirst.src": "aligned frame slots with temporary IX",
    "ffs_dfindnext.src": "aligned frame slots",
    "ffs_stat.src": "aligned frame slots",
    "ffs_getcwd.src": "aligned frame slots",
    "ffs_getlabel.src": "aligned frame slots",
}
EXPECTED_INVENTORY = (123, 48, 28, 10, 88, 126)
EXPECTED_UNALIGNED = {("mos_getError.src", 7), ("mos_getError.src", 10)}
EXPECTED_UNFRAMED_IX = {"ffs_setlabel.src"}
EXPECTED_SP_DERIVED = {"mos_flseek_p.src": 9}

IX_OFFSET = re.compile(r"\(\s*ix\s*\+\s*(?P<offset>\d+)\s*\)", re.IGNORECASE)
FRAME_SETUP = re.compile(r"\badd\s+ix\s*,\s*sp\b", re.IGNORECASE)
STACK_EXCHANGE = re.compile(r"\bex\s+\(sp\)\s*,\s*hl\b", re.IGNORECASE)
SP_BASE = re.compile(
    r"\bld\s+hl\s*,\s*(?P<offset>\d+)\s*\n\s*add\s+hl\s*,\s*sp\b",
    re.IGNORECASE,
)


class AuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class Inventory:
    sources: int
    framed: int
    stack_exchange: int
    delegated: int
    direct_rst: int
    ix_operands: int
    unaligned: frozenset[tuple[str, int]]
    unframed_ix: frozenset[str]
    sp_derived: tuple[tuple[str, int], ...]


def inventory(source_root: Path) -> Inventory:
    sources = sorted(source_root.glob("*.src"))
    framed = 0
    exchanged = 0
    delegated = 0
    direct_rst = 0
    ix_operands = 0
    unaligned: set[tuple[str, int]] = set()
    unframed_ix: set[str] = set()
    sp_derived: list[tuple[str, int]] = []
    for source in sources:
        text = source.read_text(encoding="utf-8")
        has_frame = FRAME_SETUP.search(text) is not None
        framed += has_frame
        exchanged += STACK_EXCHANGE.search(text) is not None
        delegated += "mos_getfunction" in text
        direct_rst += re.search(r"\brst\.lil\s+08h\b", text, re.IGNORECASE) is not None
        offsets = [int(match.group("offset")) for match in IX_OFFSET.finditer(text)]
        ix_operands += len(offsets)
        for offset in offsets:
            # Clang gives every <=24-bit argument a three-byte stack slot. A
            # framed wrapper therefore sees slot starts at IX+6, +9, +12, ...
            if offset < 6 or (offset - 6) % 3 != 0:
                unaligned.add((source.name, offset))
        if offsets and not has_frame:
            unframed_ix.add(source.name)
        sp_derived.extend(
            (source.name, int(match.group("offset")))
            for match in SP_BASE.finditer(text)
        )
    return Inventory(
        sources=len(sources),
        framed=framed,
        stack_exchange=exchanged,
        delegated=delegated,
        direct_rst=direct_rst,
        ix_operands=ix_operands,
        unaligned=frozenset(unaligned),
        unframed_ix=frozenset(unframed_ix),
        sp_derived=tuple(sp_derived),
    )


def run(command: list[str], *, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    if completed.returncode != 0:
        stderr = completed.stderr if isinstance(completed.stderr, str) else completed.stderr.decode("latin-1")
        raise AuditError(f"command failed ({completed.returncode}): {' '.join(command)}\n{stderr}")
    return completed.stdout


def disassemble_object(objdump: Path, object_file: Path) -> str:
    result = run([str(objdump), "-dr", str(object_file)])
    assert isinstance(result, str)
    instructions = []
    for line in result.splitlines():
        match = re.match(
            r"^\s*[0-9a-f]+:\s+(?:[0-9a-f]{2}\s+)+\s*(?P<instruction>\S.*)$",
            line,
            re.IGNORECASE,
        )
        if match:
            instructions.append(match.group("instruction"))
    return " ".join(instructions)


def archive_member(ar: Path, archive: Path, member: str, destination: Path) -> None:
    result = run([str(ar), "p", str(archive), member], binary=True)
    assert isinstance(result, bytes)
    if not result:
        raise AuditError(f"empty or absent archive member: {member}")
    destination.write_bytes(result)


def require_all(text: str, tokens: tuple[str, ...], evidence: str) -> None:
    missing = [token for token in tokens if token not in text]
    if missing:
        raise AuditError(f"{evidence} lacks: {', '.join(missing)}")


def verify_archive(ar: Path, objdump: Path, archive: Path, temporary: Path) -> None:
    expectations = {
        "mos_getError.o": (
            "ld e,(ix+6)",
            "ld hl,(ix+7)",
            "ld bc,(ix+10)",
        ),
        "ffs_setlabel.o": (
            "ex (sp),hl",
            "ld hl,(ix+6)",
            "rst.lil 0x08",
        ),
        "mos_flseek_p.o": (
            "ex (sp),hl",
            "ld hl,0x0009",
            "add hl,sp",
        ),
    }
    for member, tokens in expectations.items():
        destination = temporary / member
        archive_member(ar, archive, member, destination)
        require_all(disassemble_object(objdump, destination), tokens, member)


def verify_fixed_wrappers(
    assembler: Path, objdump: Path, include: Path, project: Path, temporary: Path
) -> None:
    expectations = {
        "mos_getError_fixed.asm": (
            "ld e,(ix+6)",
            "ld hl,(ix+9)",
            "ld bc,(ix+12)",
        ),
        "ffs_setlabel_fixed.asm": (
            "ex (sp),hl",
            "ld a,0xa4",
            "rst.lil 0x08",
        ),
        "mos_flseek_p_fixed.asm": (
            "ex (sp),hl",
            "ld hl,0x0006",
            "add hl,sp",
        ),
    }
    for name, tokens in expectations.items():
        source = project / "src" / name
        destination = temporary / (source.stem + ".o")
        run(
            [
                str(assembler),
                "-march=ez80+full",
                "-I",
                str(include),
                str(source),
                "-o",
                str(destination),
            ]
        )
        disassembly = disassemble_object(objdump, destination)
        require_all(disassembly, tokens, name)
        if name == "ffs_setlabel_fixed.asm" and "(ix+" in disassembly:
            raise AuditError("corrected ffs_setlabel still reads through IX")


def verify_compiler_abi(
    compiler: Path, objdump: Path, include: Path, project: Path, temporary: Path
) -> None:
    object_file = temporary / "abi_slot_probe.o"
    run(
        [
            str(compiler),
            "-mllvm",
            "-z80-gas-style",
            "-mllvm",
            "-z80-print-zero-offset",
            "-nostdinc",
            "-isystem",
            str(include),
            "-target",
            "ez80-none-elf",
            "-Oz",
            "-Wa,-march=ez80+full",
            "-c",
            str(project / "audit/abi_slot_probe.c"),
            "-o",
            str(object_file),
        ]
    )
    disassembly = disassemble_object(objdump, object_file)
    require_all(
        disassembly,
        (
            "ld de,0xabcdef push de push hl ld hl,0x0012 push hl call",
            "ld hl,0xabcdef ld de,0xffff89 push de push hl ld hl,0x0034 push hl call",
        ),
        "Clang ABI call-site disassembly",
    )


def verify_contract_coverage(source_root: Path) -> None:
    missing = sorted(name for name in CONTRACT_WRAPPERS if not (source_root / name).is_file())
    if missing:
        raise AuditError("contract wrapper sources are missing: " + ", ".join(missing))


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parent
    repository = project.parents[1]
    release = (repository / "toolchains/agondev").resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=release.parent / "src/lib/libmos")
    parser.add_argument("--release", type=Path, default=release)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = args.source.resolve()
    release = args.release.resolve()
    project = Path(__file__).resolve().parent
    tools = release / "bin"
    include = release / "include"
    archive = release / "lib/libagon.a"
    result = inventory(source_root)
    try:
        if result.unaligned != EXPECTED_UNALIGNED:
            raise AuditError(f"unexpected unaligned IX operands: {sorted(result.unaligned)}")
        actual_inventory = (
            result.sources,
            result.framed,
            result.stack_exchange,
            result.delegated,
            result.direct_rst,
            result.ix_operands,
        )
        if actual_inventory != EXPECTED_INVENTORY:
            raise AuditError(
                f"pinned wrapper inventory changed: expected {EXPECTED_INVENTORY}, "
                f"got {actual_inventory}"
            )
        if result.unframed_ix != EXPECTED_UNFRAMED_IX:
            raise AuditError(f"unexpected unframed IX users: {sorted(result.unframed_ix)}")
        if dict(result.sp_derived) != EXPECTED_SP_DERIVED:
            raise AuditError(f"unexpected SP-derived argument pointers: {result.sp_derived}")
        verify_contract_coverage(source_root)
        with tempfile.TemporaryDirectory(prefix="libmos-wrapper-audit-") as directory:
            temporary = Path(directory)
            verify_archive(
                tools / "ez80-none-elf-ar",
                tools / "ez80-none-elf-objdump",
                archive,
                temporary,
            )
            verify_fixed_wrappers(
                tools / "ez80-none-elf-as",
                tools / "ez80-none-elf-objdump",
                include,
                project,
                temporary,
            )
            verify_compiler_abi(
                tools / "ez80-none-elf-clang",
                tools / "ez80-none-elf-objdump",
                include,
                project,
                temporary,
            )
    except (AuditError, OSError) as error:
        print(f"audit_wrappers.py: {error}", file=subprocess.sys.stderr)
        return 1

    print(
        "libmos wrapper audit: "
        f"{result.sources} sources; {result.framed} framed, "
        f"{result.stack_exchange} stack-exchange, {result.delegated} delegated, "
        f"{result.direct_rst} direct RST; {result.ix_operands} IX operands"
    )
    print("confirmed defects: mos_getError +7/+10; ffs_setlabel unframed IX; mos_flseek_p SP+9")
    print("contract wrappers:")
    for name, status in CONTRACT_WRAPPERS.items():
        print(f"  {name.removesuffix('.src')}: {status}")
    print(
        "coverage limit: static wrapper/source/archive and compiler call slots only; "
        "delegated MOS C functions, RST semantics, return widening, and hardware are not proven"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
