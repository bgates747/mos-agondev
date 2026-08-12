#!/usr/bin/env python3
"""Run the AgonDev contract MOSlet against candidate and reference MOS."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


class ContractError(RuntimeError):
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FAB_ROOT = PROJECT_ROOT / "fab-agon-emulator"
SPARSE_FIXTURE_SIZE = 0x01020305
MAX_OUTPUT_BYTES = 1024 * 1024
TARGET_GOLDEN = re.compile(
    r'TARGET_GOLDEN_PATTERN\(\s*"(?P<pattern>(?:\\.|[^"\\])*)"\s*\)'
)


def find_cli(fab_root: Path) -> Path:
    candidates = (
        fab_root / "target/release/agon-cli-emulator",
        fab_root / "agon-cli-emulator",
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise ContractError(
        "Fab CLI emulator is missing or not executable; checked:\n"
        + "\n".join(f"  {candidate}" for candidate in candidates)
    )


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fixture_snapshot(root: Path) -> tuple[tuple[str, str, int, int, str], ...]:
    """Describe every fixture entry without following links."""
    entries: list[tuple[str, str, int, int, str]] = []
    paths = [root, *sorted(root.rglob("*"))]
    for path in paths:
        relative = "." if path == root else str(path.relative_to(root))
        if path.is_symlink():
            raise ContractError(f"contract hostfs acquired a symlink: {relative}")
        mode = path.stat().st_mode & 0o777
        if path.is_dir():
            entries.append((relative, "directory", mode, 0, ""))
        elif path.is_file():
            entries.append(
                (relative, "file", mode, path.stat().st_size, digest_file(path))
            )
        else:
            raise ContractError(f"contract hostfs has a special entry: {relative}")
    return tuple(entries)


def create_fixture(root: Path, binary: Path) -> None:
    if root.exists() and any(root.iterdir()):
        raise ContractError(f"contract hostfs is not empty: {root}")
    (root / binary.name).write_bytes(binary.read_bytes())
    sparse = root / "abi-sparse.bin"
    with sparse.open("wb") as output:
        output.seek(SPARSE_FIXTURE_SIZE - 1)
        output.write(b"Q")
    (root / "seek.txt").write_bytes(b"0123456789")
    (root / "lines.txt").write_bytes(b"line-one\nline-two\n")
    nested = root / "nested"
    nested.mkdir()
    (nested / "alpha.txt").write_bytes(b"alpha-data\n")


def set_fixture_read_only(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            path.chmod(0o444)
    for path in sorted(
        (entry for entry in root.rglob("*") if entry.is_dir()), reverse=True
    ):
        path.chmod(0o555)
    root.chmod(0o555)


def restore_fixture_modes(root: Path) -> None:
    """Make a temporary fixture removable after a read-only target run."""
    root.chmod(0o755)
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            path.chmod(0o755)
        elif path.is_file() and not path.is_symlink():
            path.chmod(0o644)


def validate_output(output: bytes, firmware: Path) -> bytes:
    # Fab's fake VDP presents rendered lines with LF only; the target MOSlet
    # separately checks printf's byte count and the host golden checks raw CR/LF.
    required = (b"CONTRACT-BEGIN\n", b"FORMAT-PRINTF\n", b"CONTRACT-PASS\n")
    positions: list[int] = []
    search_from = 0
    for token in required:
        position = output.find(token, search_from)
        if position < 0:
            raise ContractError(
                f"missing ordered {token!r} for {firmware}:\n"
                f"{output.decode('latin-1')}"
            )
        positions.append(position)
        search_from = position + len(token)
    if b"CONTRACT-FAIL" in output or b"CONTRACT-FAILED" in output:
        raise ContractError(
            f"contract MOSlet reported failure for {firmware}:\n"
            + output.decode("latin-1")
        )
    begin = positions[0]
    end = positions[-1] + len(required[-1])
    return output[begin:end]


def verify_target_format_coverage(project: Path) -> None:
    """Tie the target MOSlet's one-per-spelling markers to the MOS inventory."""
    scanner = project / "projects/mos-port/runtime/scan_formats.py"
    result = subprocess.run(
        [sys.executable, "-B", str(scanner), "--json"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise ContractError("MOS format inventory failed:\n" + result.stderr)
    try:
        used = set(json.loads(result.stdout)["specifiers"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ContractError("MOS format inventory output is malformed") from error
    source = (project / "projects/contract-probe/src/main.c").read_text(
        encoding="utf-8"
    )
    marked = [
        ast.literal_eval('"' + match.group("pattern") + '"')
        for match in TARGET_GOLDEN.finditer(source)
    ]
    duplicates = sorted(pattern for pattern in set(marked) if marked.count(pattern) > 1)
    missing = sorted(used - set(marked))
    extra = sorted(set(marked) - used)
    if duplicates or missing or extra:
        details = []
        if duplicates:
            details.append("duplicates=" + ",".join(duplicates))
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        raise ContractError("target formatter coverage drift: " + "; ".join(details))


def run(cli: Path, firmware: Path, sdcard: Path, timeout: float) -> bytes:
    if timeout <= 0:
        raise ContractError("timeout must be positive")
    try:
        completed = subprocess.run(
            [
                str(cli),
                "--mos",
                str(firmware),
                "--sdcard",
                str(sdcard),
                "--unlimited-cpu",
                "--zero",
            ],
            input=b"mos-contract-probe.bin\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise ContractError(f"emulator timed out for {firmware}") from error
    if completed.returncode != 0:
        raise ContractError(
            f"emulator exited {completed.returncode} for {firmware}"
        )
    if not completed.stdout:
        raise ContractError(f"emulator produced no output for {firmware}")
    if len(completed.stdout) > MAX_OUTPUT_BYTES:
        raise ContractError(
            f"emulator output exceeded {MAX_OUTPUT_BYTES} bytes for {firmware}"
        )
    return validate_output(completed.stdout, firmware)


def verify_artifacts(root: Path, objdump: Path) -> None:
    map_text = (root / "bin/mos-contract-probe.map").read_text(encoding="utf-8")
    for required in (
        "obj/firmware_printf.o",
        "obj/mos_getError_fixed.o",
        "obj/ffs_setlabel_fixed.o",
        "obj/mos_flseek_p_fixed.o",
    ):
        if required not in map_text:
            raise ContractError(f"contract map omits required local object: {required}")
    if re.search(r"(?:^|/)nanoprintf\.o\b", map_text, re.MULTILINE):
        raise ContractError("contract MOSlet selected libagon's nanoprintf.o")

    expected_runtime_wrappers = {
        "mos_extractstring.o",
        "mos_extractnumber.o",
        "mos_gsinit.o",
        "mos_gsread.o",
        "mos_substituteargs.o",
        "mos_resolvepath.o",
        "mos_fread.o",
        "mos_getfil.o",
        "mos_feof.o",
        "ffs_fgets.o",
        "ffs_ferror.o",
        "ffs_flseek_p.o",
        "ffs_dopen.o",
        "ffs_dread.o",
        "ffs_dclose.o",
        "ffs_dfindfirst.o",
        "ffs_dfindnext.o",
        "ffs_stat.o",
        "ffs_getcwd.o",
        "ffs_getlabel.o",
    }
    missing_wrappers = sorted(
        name
        for name in expected_runtime_wrappers
        if not re.search(rf"libagon\.a\({re.escape(name)}\)", map_text)
    )
    if missing_wrappers:
        raise ContractError(
            "contract map omits expanded runtime wrappers: "
            + ", ".join(missing_wrappers)
        )

    wrapper = subprocess.run(
        [str(objdump), "-dr", str(root / "obj/mos_getError_fixed.o")],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    expected = ("ld e,(ix+6)", "ld hl,(ix+9)", "ld bc,(ix+12)", "rst.lil 0x08")
    normalized = re.sub(r"\s+", " ", wrapper)
    if not all(instruction in normalized for instruction in expected):
        raise ContractError("corrected mos_getError stack-slot disassembly changed")

    fixed_wrappers = {
        "ffs_setlabel_fixed.o": ("ex (sp),hl", "ld a,0xa4", "rst.lil 0x08"),
        "mos_flseek_p_fixed.o": ("ld hl,0x0006", "add hl,sp", "rst.lil 0x08"),
    }
    for object_name, instructions in fixed_wrappers.items():
        disassembly = subprocess.run(
            [str(objdump), "-dr", str(root / "obj" / object_name)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
        normalized = re.sub(r"\s+", " ", disassembly)
        if not all(instruction in normalized for instruction in instructions):
            raise ContractError(f"corrected {object_name} disassembly changed")


def main() -> int:
    project = PROJECT_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fab-root", type=Path, default=DEFAULT_FAB_ROOT)
    parser.add_argument(
        "--cli",
        type=Path,
        help="explicit Fab CLI executable (default: discover under --fab-root)",
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=project / "projects/mos-port/bin/MOS.bin",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=project / "emulator/firmware/mos_platform.bin",
    )
    parser.add_argument(
        "--binary", type=Path, default=Path(__file__).resolve().parent / "bin/mos-contract-probe.bin"
    )
    parser.add_argument(
        "--objdump",
        type=Path,
        default=project / "toolchains/agondev/bin/ez80-none-elf-objdump",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--show-contract",
        action="store_true",
        help="print the normalized candidate and reference contract blocks",
    )
    args = parser.parse_args()

    try:
        cli = (
            args.cli.expanduser().resolve()
            if args.cli
            else find_cli(args.fab_root.expanduser().resolve())
        )
    except (ContractError, OSError) as error:
        print(f"verify_contract.py: {error}", file=sys.stderr)
        return 1

    for path, label in (
        (cli, "Fab CLI"),
        (args.candidate, "candidate MOS"),
        (args.reference, "reference MOS"),
        (args.binary, "contract MOSlet"),
        (args.objdump, "AgonDev objdump"),
    ):
        if not path.is_file():
            raise SystemExit(f"missing {label}: {path}")

    try:
        verify_target_format_coverage(project)
        verify_artifacts(Path(__file__).resolve().parent, args.objdump.resolve())
        with tempfile.TemporaryDirectory(prefix="mos-contract-sd-") as temporary:
            sdcard = Path(temporary)
            create_fixture(sdcard, args.binary)
            set_fixture_read_only(sdcard)
            expected_fixture = fixture_snapshot(sdcard)
            try:
                candidate = run(
                    cli, args.candidate.resolve(), sdcard, args.timeout
                )
                if fixture_snapshot(sdcard) != expected_fixture:
                    raise ContractError("candidate changed the read-only hostfs fixture")
                reference = run(
                    cli, args.reference.resolve(), sdcard, args.timeout
                )
                if fixture_snapshot(sdcard) != expected_fixture:
                    raise ContractError("reference changed the read-only hostfs fixture")
            finally:
                restore_fixture_modes(sdcard)
    except (ContractError, OSError, subprocess.SubprocessError) as error:
        print(f"verify_contract.py: {error}", file=sys.stderr)
        return 1

    if candidate != reference:
        print(
            "verify_contract.py: candidate/reference contract output differs\n"
            "candidate:\n"
            + candidate.decode("latin-1")
            + "reference:\n"
            + reference.decode("latin-1"),
            file=subprocess.sys.stderr,
        )
        return 1
    if args.show_contract:
        print("candidate:\n" + candidate.decode("latin-1"), end="")
        print("reference:\n" + reference.decode("latin-1"), end="")
    print(
        "MOS contract verified on candidate and ZDS reference: target formatter "
        "boundaries plus C/RST API argument and return paths"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
