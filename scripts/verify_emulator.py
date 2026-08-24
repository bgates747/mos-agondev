#!/usr/bin/env python3
"""Read-only verification for the project-local stock emulator profile."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import setup_emulator


PROJECT_ROOT = Path(__file__).absolute().parent.parent
DEFAULT_PROFILE = PROJECT_ROOT / "emulator"
DEFAULT_FAB_ROOT = PROJECT_ROOT / "fab-agon-emulator"


class VerificationError(RuntimeError):
    """Raised when one or more profile invariants do not hold."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("\n".join(self.errors))


@dataclass(frozen=True)
class VerificationResult:
    profile: Path
    executable: Path
    mos: Path
    vdp: Path
    local_bin_overrides: tuple[Path, ...]
    hashes: dict[str, str]


def absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def emulator_executable(fab_root: Path) -> Path | None:
    for candidate in (
        fab_root / "fab-agon-emulator",
        fab_root / "target/release/fab-agon-emulator",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolved(path: Path, errors: list[str], label: str) -> Path | None:
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        errors.append(f"Broken {label}: {path} ({error})")
        return None


def _expect_symlink(
    path: Path,
    expected: Path,
    errors: list[str],
    label: str,
) -> None:
    if not path.is_symlink():
        errors.append(f"Expected {label} symlink: {path}")
        return
    actual_resolved = _resolved(path, errors, label)
    expected_resolved = _resolved(expected, errors, f"expected {label} target")
    if (
        actual_resolved is not None
        and expected_resolved is not None
        and actual_resolved != expected_resolved
    ):
        errors.append(
            f"Wrong {label} target: {path} -> {actual_resolved}; "
            f"expected {expected_resolved}"
        )


def _expect_real_writable_directory(
    path: Path,
    errors: list[str],
    label: str,
) -> None:
    if path.is_symlink() or not path.is_dir():
        errors.append(f"Expected real {label} directory: {path}")
        return
    if not os.access(path, os.W_OK):
        errors.append(f"Expected writable {label} directory: {path}")


def verify_profile(profile: Path, fab_root: Path) -> VerificationResult:
    """Verify profile topology and stock identities without modifying it."""

    profile = absolute_path(profile)
    fab_root = absolute_path(fab_root)
    errors: list[str] = []
    overrides: list[Path] = []

    if profile.is_symlink() or not profile.is_dir():
        raise VerificationError((f"Expected real emulator profile directory: {profile}",))

    expected_executable = emulator_executable(fab_root)
    if expected_executable is None:
        errors.append(f"No executable Fab emulator found under {fab_root}")
        expected_executable = fab_root / "fab-agon-emulator"

    firmware = fab_root / "firmware"
    shared_sdcard = fab_root / "sdcard"
    mos = firmware / "mos_platform.bin"
    mos_map = firmware / "mos_platform.map"
    vdp = firmware / "vdp_platform.so"
    shared_bin = shared_sdcard / "bin"

    for path, label in (
        (firmware, "stock firmware directory"),
        (mos, "stock Platform MOS"),
        (mos_map, "stock Platform MOS map"),
        (vdp, "stock Platform VDP module"),
        (shared_bin, "shared stock /bin"),
        (shared_sdcard / "mos", "shared stock /mos"),
        (shared_sdcard / "MOS.bin", "MOS update payload"),
        (shared_sdcard / "firmware.bin", "VDP update payload"),
    ):
        if not path.exists():
            errors.append(f"Missing {label}: {path}")

    launcher = profile / "fab-agon-emulator"
    if launcher.is_symlink() or not launcher.is_file():
        errors.append(f"Expected real generated Fab launcher: {launcher}")
    else:
        try:
            launcher_text = launcher.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"Could not read generated Fab launcher: {launcher} ({error})")
        else:
            if launcher_text != setup_emulator.generated_launcher_text():
                errors.append(f"Generated Fab launcher content drifted: {launcher}")
            if not os.access(launcher, os.X_OK):
                errors.append(f"Generated Fab launcher is not executable: {launcher}")
    _expect_symlink(
        profile / "fab-agon-emulator.bin",
        expected_executable,
        errors,
        "raw Fab executable",
    )
    _expect_symlink(profile / "firmware", firmware, errors, "stock firmware")

    marker = profile / ".bespoke-vdp-profile"
    if marker.exists() or marker.is_symlink():
        errors.append(f"Stock profile contains bespoke VDP marker: {marker}")

    sdcard = profile / "sdcard"
    profile_bin = sdcard / "bin"
    agondev = sdcard / "agondev"
    _expect_real_writable_directory(sdcard, errors, "SD-card root")
    _expect_real_writable_directory(profile_bin, errors, "/bin overlay")
    _expect_real_writable_directory(agondev, errors, "AgonDev staging")

    _expect_symlink(
        sdcard / "mos", shared_sdcard / "mos", errors, "stock /mos"
    )
    _expect_symlink(
        sdcard / "MOS.bin",
        shared_sdcard / "MOS.bin",
        errors,
        "MOS update payload",
    )
    _expect_symlink(
        sdcard / "firmware.bin",
        shared_sdcard / "firmware.bin",
        errors,
        "VDP update payload",
    )

    if shared_bin.is_dir() and profile_bin.is_dir() and not profile_bin.is_symlink():
        sources = sorted(path for path in shared_bin.iterdir() if path.is_file())
        if not sources:
            errors.append(f"Shared stock /bin is empty: {shared_bin}")
        for source in sources:
            destination = profile_bin / source.name
            if destination.is_symlink():
                _expect_symlink(
                    destination,
                    source,
                    errors,
                    f"stock /bin/{source.name}",
                )
            elif destination.is_file():
                overrides.append(destination)
            else:
                errors.append(f"Missing stock /bin entry: {destination}")

        for destination in profile_bin.iterdir():
            if destination.is_symlink():
                _resolved(destination, errors, f"/bin link {destination.name}")

    autoexec = sdcard / "autoexec.txt"
    if autoexec.is_symlink() or not autoexec.is_file():
        errors.append(f"Expected regular profile autoexec: {autoexec}")
    else:
        autoexec_bytes = autoexec.read_bytes()
        if b"\n" in autoexec_bytes.replace(b"\r\n", b""):
            errors.append(f"Autoexec contains a bare LF instead of CRLF: {autoexec}")

    if errors:
        raise VerificationError(errors)

    assert expected_executable is not None
    hashes = {
        "fab": sha256(expected_executable),
        "mos_platform": sha256(mos),
        "vdp_platform": sha256(vdp),
    }
    return VerificationResult(
        profile=profile,
        executable=expected_executable,
        mos=mos,
        vdp=vdp,
        local_bin_overrides=tuple(overrides),
        hashes=hashes,
    )


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE,
        help=f"profile directory (default: {DEFAULT_PROFILE})",
    )
    parser.add_argument(
        "--fab-root",
        type=Path,
        default=DEFAULT_FAB_ROOT,
        help=f"stock Fab checkout (default: {DEFAULT_FAB_ROOT})",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="report only errors",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        result = verify_profile(arguments.profile, arguments.fab_root)
    except VerificationError as error:
        for message in error.errors:
            print(f"verify_emulator.py: {message}", file=sys.stderr)
        return 1

    if not arguments.quiet:
        print(f"Verified profile: {result.profile}")
        print(f"Fab SHA-256:      {result.hashes['fab']}")
        print(f"MOS SHA-256:      {result.hashes['mos_platform']}")
        print(f"VDP SHA-256:      {result.hashes['vdp_platform']}")
        for override in result.local_bin_overrides:
            print(f"Local /bin override preserved: {override}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
