#!/usr/bin/env python3
"""Boot the AgonDev MOS in Fab's CLI emulator and verify hostfs startup."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


REQUIRED_OUTPUT = (
    b"Agon Platform MOS Version",
    b"Volume: hostfs",
    b"Directory: /",
)
FORBIDDEN_OUTPUT = (
    b"No SD card present",
    b"Invalid command",
    b"hostfs integration disabled",
)


class BootError(RuntimeError):
    """The custom firmware did not reach a usable hostfs-backed shell."""


def find_cli(fab_root: Path) -> Path:
    candidates = (
        fab_root / "target/release/agon-cli-emulator",
        fab_root / "agon-cli-emulator",
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise BootError(
        "Fab CLI emulator is missing or not executable; checked:\n"
        + "\n".join(f"  {candidate}" for candidate in candidates)
    )


def validate_output(output: bytes) -> None:
    missing = [token for token in REQUIRED_OUTPUT if token not in output]
    forbidden = [token for token in FORBIDDEN_OUTPUT if token in output]
    if missing or forbidden:
        details = []
        if missing:
            details.append("missing " + ", ".join(repr(token) for token in missing))
        if forbidden:
            details.append("found " + ", ".join(repr(token) for token in forbidden))
        raise BootError("custom MOS boot output failed: " + "; ".join(details))


def verify_boot(cli: Path, firmware: Path, sdcard: Path, timeout: float) -> bytes:
    for path, label in ((firmware, "firmware image"), (sdcard, "SD-card root")):
        if not path.exists():
            raise BootError(f"missing {label}: {path}")
    if not firmware.is_file():
        raise BootError(f"firmware image is not a regular file: {firmware}")
    if not sdcard.is_dir():
        raise BootError(f"SD-card root is not a directory: {sdcard}")

    try:
        completed = subprocess.run(
            [
                os.fspath(cli),
                "--mos",
                os.fspath(firmware),
                "--sdcard",
                os.fspath(sdcard),
                "--unlimited-cpu",
                "--zero",
            ],
            input=b"dir\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise BootError(f"custom MOS boot exceeded {timeout:g} seconds") from error
    if completed.returncode != 0:
        raise BootError(f"Fab CLI emulator exited with status {completed.returncode}")
    validate_output(completed.stdout)
    return completed.stdout


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fab-root", type=Path, default=root / "../../fab-agon-emulator")
    parser.add_argument("--firmware", type=Path, default=root / "projects/mos-port/bin/MOS.bin")
    parser.add_argument("--sdcard", type=Path, default=root / "emulator/sdcard")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    try:
        cli = find_cli(args.fab_root.expanduser().resolve())
        output = verify_boot(cli, args.firmware.resolve(), args.sdcard.resolve(), args.timeout)
    except BootError as error:
        print(f"verify_boot.py: {error}", file=os.sys.stderr)
        return 1
    print(
        "Custom MOS boot verified: shell banner, hostfs mount, and directory command "
        f"({len(output)} output bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
