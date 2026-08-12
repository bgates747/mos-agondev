#!/usr/bin/env python3
"""Compare deterministic, read-only MOS shell behavior with the ZDS image."""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import tempfile
from pathlib import Path

import verify_boot


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FAB_ROOT = PROJECT_ROOT / "fab-agon-emulator"


COMMANDS = (
    b"help\n"
    b"help echo\n"
    b"echo AgonDev parity\n"
    b"set PortTest a value with spaces\n"
    b"show PortTest\n"
    b"unset PortTest\n"
    b"show PortTest\n"
    b"time\n"
    b"credits\n"
    b"dir\n"
    b"type root.txt\n"
    b"type raw.txt\n"
    b"cd nested\n"
    b"dir\n"
    b"type inner.txt\n"
    b"cd deeper\n"
    b"dir\n"
    b"type final.txt\n"
    b"cd /\n"
    b"type nested/deeper/final.txt\n"
    b"cd absent\n"
    b"type absent.txt\n"
    b"this-command-does-not-exist\n"
)
START_MARKER = b"Agon Platform MOS Version"
MAX_OUTPUT_BYTES = 1024 * 1024
NOISE_PREFIXES = (
    b"Tom's Fake VDP Version",
    b"unknown packet VDU",
    b"uunknown packet VDU",
)
FIXTURE_FILES = {
    "root.txt": b"ROOT-TEXT: alpha beta 0123456789\r\n",
    "raw.txt": b"RAW-TEXT:A  B_C(no-final-newline)",
    "nested/inner.txt": b"INNER-TEXT: punctuation !@#$%^&*()[]{}\r\n",
    "nested/deeper/final.txt": b"FINAL-TEXT: exact hostfs bytes\r\n",
}
REQUIRED_TRANSCRIPT_TOKENS = (
    "AgonDev parity",
    "a value with spaces",
    "ROOT-TEXT: alpha beta 0123456789",
    "RAW-TEXT:A  B_C(no-final-newline)",
    "INNER-TEXT: punctuation !@#$%^&*()[]{}",
    "FINAL-TEXT: exact hostfs bytes",
    "Directory: /nested",
    "Directory: /nested/deeper",
    "Could not find file",
    "Invalid command",
)


class ParityError(RuntimeError):
    """The candidate and reference produced different stable shell output."""


def create_fixture(root: Path) -> None:
    """Create the complete disposable hostfs corpus used by both images."""
    if root.exists() and any(root.iterdir()):
        raise ParityError(f"hostfs fixture root is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    for relative, payload in FIXTURE_FILES.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)


def validate_fixture(root: Path) -> None:
    """Prove that an emulator run did not alter the curated hostfs corpus."""
    expected_files = set(FIXTURE_FILES)
    expected_directories = {
        str(parent)
        for relative in FIXTURE_FILES
        for parent in Path(relative).parents
        if str(parent) != "."
    }
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for path in root.rglob("*"):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            raise ParityError(f"hostfs fixture acquired a symlink: {relative}")
        if path.is_dir():
            actual_directories.add(relative)
        elif path.is_file():
            actual_files.add(relative)
        else:
            raise ParityError(f"hostfs fixture acquired a special file: {relative}")
    if actual_files != expected_files or actual_directories != expected_directories:
        raise ParityError("hostfs fixture structure changed during parity run")
    for relative, expected in FIXTURE_FILES.items():
        if (root / relative).read_bytes() != expected:
            raise ParityError(f"hostfs fixture content changed: {relative}")


def run(cli: Path, firmware: Path, sdcard: Path, timeout: float) -> bytes:
    if timeout <= 0:
        raise ParityError("timeout must be positive")
    for path, kind in ((cli, "emulator"), (firmware, "firmware")):
        if not path.is_file():
            raise ParityError(f"missing {kind} file: {path}")
    if not os.access(cli, os.X_OK):
        raise ParityError(f"emulator is not executable: {cli}")
    if not sdcard.is_dir():
        raise ParityError(f"missing hostfs directory: {sdcard}")
    try:
        completed = subprocess.run(
            [
                str(cli), "--mos", str(firmware), "--sdcard", str(sdcard),
                "--unlimited-cpu", "--zero",
            ],
            input=COMMANDS,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise ParityError(f"emulator exceeded {timeout:g} seconds for {firmware}") from error
    if completed.returncode != 0:
        raise ParityError(f"emulator exited {completed.returncode} for {firmware}")
    if not completed.stdout:
        raise ParityError(f"emulator produced no output for {firmware}")
    if len(completed.stdout) > MAX_OUTPUT_BYTES:
        raise ParityError(
            f"emulator output exceeded {MAX_OUTPUT_BYTES} bytes for {firmware}"
        )
    return completed.stdout


def normalize(output: bytes) -> list[str]:
    output = output.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    marker = output.find(START_MARKER)
    if marker < 0:
        raise ParityError("MOS banner is absent")
    lines = []
    for raw in output[marker:].splitlines():
        line = raw.strip(b"\x00\x80 ")
        if not line or any(line.startswith(prefix) for prefix in NOISE_PREFIXES):
            continue
        # The first prompt reflects the candidate's initialized current-dir
        # buffer but both images must settle on the hostfs root before commands.
        lines.append(line.decode("latin-1"))
    return lines


def compare(candidate: bytes, reference: bytes) -> None:
    candidate_lines = normalize(candidate)
    reference_lines = normalize(reference)
    if candidate_lines != reference_lines:
        diff = "\n".join(
            difflib.unified_diff(
                reference_lines,
                candidate_lines,
                fromfile="ZDS reference",
                tofile="AgonDev candidate",
                lineterm="",
            )
        )
        raise ParityError("stable shell output differs:\n" + diff)
    transcript = "\n".join(candidate_lines)
    missing = [token for token in REQUIRED_TRANSCRIPT_TOKENS if token not in transcript]
    missing_commands = [
        command.decode("ascii")
        for command in COMMANDS.splitlines()
        if "*" + command.decode("ascii") not in transcript
    ]
    if missing:
        raise ParityError(
            "matching transcripts lack required command evidence: " + ", ".join(missing)
        )
    if missing_commands:
        raise ParityError(
            "matching transcripts did not execute commands: " + ", ".join(missing_commands)
        )
    # The value occurs in the SET command and the first SHOW output. A third
    # occurrence would mean that UNSET failed and the second SHOW still printed it.
    if transcript.count("a value with spaces") != 2:
        raise ParityError("matching transcripts do not prove SET/SHOW/UNSET state")


def main() -> int:
    project = PROJECT_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fab-root", type=Path, default=DEFAULT_FAB_ROOT)
    parser.add_argument("--candidate", type=Path, default=project / "projects/mos-port/bin/MOS.bin")
    parser.add_argument("--reference", type=Path, default=project / "emulator/firmware/mos_platform.bin")
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()
    try:
        cli = verify_boot.find_cli(args.fab_root.expanduser().resolve())
        with tempfile.TemporaryDirectory(prefix="mos-parity-hostfs-") as temporary:
            sdcard = Path(temporary)
            create_fixture(sdcard)
            validate_fixture(sdcard)
            candidate = run(cli, args.candidate.resolve(), sdcard, args.timeout)
            validate_fixture(sdcard)
            reference = run(cli, args.reference.resolve(), sdcard, args.timeout)
            validate_fixture(sdcard)
            compare(candidate, reference)
    except (OSError, ParityError, verify_boot.BootError) as error:
        print(f"compare_boot.py: {error}", file=subprocess.sys.stderr)
        return 1
    print(
        "MOS shell parity verified: command/help parsing, variables, RTC, "
        "credits, curated hostfs traversal/TYPE bytes, and error handling"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
