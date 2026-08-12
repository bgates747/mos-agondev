#!/usr/bin/env python3
"""Provision the project-local stock Fab Agon Emulator profile."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).absolute().parent.parent
DEFAULT_PROFILE = PROJECT_ROOT / "emulator"
DEFAULT_FAB_ROOT = PROJECT_ROOT / "fab-agon-emulator"
DEFAULT_AUTOEXEC = b"SET KEYBOARD 1\r\n"


class SetupError(RuntimeError):
    """Raised when provisioning cannot proceed without risking local data."""


@dataclass(frozen=True)
class RuntimeInputs:
    fab_root: Path
    executable: Path
    firmware: Path
    mos: Path
    mos_map: Path
    vdp: Path
    shared_bin: Path
    shared_mos: Path
    update_mos: Path
    update_vdp: Path


def absolute_path(path: Path) -> Path:
    """Return an absolute path without resolving away a final symlink."""

    return Path(os.path.abspath(path.expanduser()))


def emulator_executable(fab_root: Path) -> Path:
    """Select the executable layout supported by the canonical environment."""

    candidates = (
        fab_root / "fab-agon-emulator",
        fab_root / "target/release/fab-agon-emulator",
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise SetupError(
        "Fab emulator executable is missing or not executable; checked:\n"
        + "\n".join(f"  {candidate}" for candidate in candidates)
    )


def runtime_inputs(fab_root: Path) -> RuntimeInputs:
    """Validate every upstream input before making any profile change."""

    fab_root = absolute_path(fab_root)
    firmware = fab_root / "firmware"
    shared_sdcard = fab_root / "sdcard"
    inputs = RuntimeInputs(
        fab_root=fab_root,
        executable=emulator_executable(fab_root),
        firmware=firmware,
        mos=firmware / "mos_platform.bin",
        mos_map=firmware / "mos_platform.map",
        vdp=firmware / "vdp_platform.so",
        shared_bin=shared_sdcard / "bin",
        shared_mos=shared_sdcard / "mos",
        update_mos=shared_sdcard / "MOS.bin",
        update_vdp=shared_sdcard / "firmware.bin",
    )
    required = (
        inputs.firmware,
        inputs.mos,
        inputs.mos_map,
        inputs.vdp,
        inputs.shared_bin,
        inputs.shared_mos,
        inputs.update_mos,
        inputs.update_vdp,
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        raise SetupError(
            "Required stock emulator inputs are missing:\n"
            + "\n".join(f"  {path}" for path in missing)
        )
    if not inputs.firmware.is_dir():
        raise SetupError(f"Expected firmware directory: {inputs.firmware}")
    if not inputs.shared_bin.is_dir():
        raise SetupError(f"Expected shared /bin directory: {inputs.shared_bin}")
    if not inputs.shared_mos.is_dir():
        raise SetupError(f"Expected shared /mos directory: {inputs.shared_mos}")
    if not stock_bin_files(inputs.shared_bin):
        raise SetupError(f"Shared /bin directory is empty: {inputs.shared_bin}")
    return inputs


def stock_bin_files(shared_bin: Path) -> tuple[Path, ...]:
    """Return the regular stock tools exposed through the writable overlay."""

    return tuple(sorted(path for path in shared_bin.iterdir() if path.is_file()))


def _existing_kind(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "special path"


def _require_real_directory_or_absent(path: Path, label: str) -> None:
    if path.is_symlink():
        raise SetupError(f"Refusing symlinked {label}: {path}")
    if path.exists() and not path.is_dir():
        raise SetupError(f"Refusing non-directory {label}: {path}")


def _require_replaceable_link(path: Path, label: str) -> None:
    if path.is_symlink() or not path.exists():
        return
    raise SetupError(
        f"Refusing to replace real local {_existing_kind(path)} for {label}: {path}"
    )


def preflight_profile(profile: Path, inputs: RuntimeInputs) -> tuple[Path, ...]:
    """Reject unsafe or incompatible state before changing any path."""

    profile = absolute_path(profile)
    filesystem_root = Path(profile.anchor)
    if profile == filesystem_root:
        raise SetupError("Refusing to use the filesystem root as an emulator profile")
    if profile == inputs.fab_root:
        raise SetupError("The emulator profile must not be the Fab checkout")
    if profile in inputs.fab_root.parents or inputs.fab_root in profile.parents:
        raise SetupError(
            "The emulator profile and Fab checkout must not contain one another"
        )

    sdcard = profile / "sdcard"
    profile_bin = sdcard / "bin"
    agondev = sdcard / "agondev"
    autoexec = sdcard / "autoexec.txt"
    marker = profile / ".bespoke-vdp-profile"

    _require_real_directory_or_absent(profile, "profile")
    _require_real_directory_or_absent(sdcard, "SD-card root")
    if profile_bin.exists() and not profile_bin.is_symlink() and not profile_bin.is_dir():
        raise SetupError(f"Refusing non-directory /bin overlay: {profile_bin}")
    _require_real_directory_or_absent(agondev, "AgonDev staging directory")

    if marker.exists() or marker.is_symlink():
        raise SetupError(
            "Refusing stock setup while a bespoke VDP marker exists: " f"{marker}"
        )

    for path, label in (
        (profile / "fab-agon-emulator", "Fab executable link"),
        (profile / "firmware", "stock firmware link"),
        (sdcard / "mos", "stock /mos link"),
        (sdcard / "MOS.bin", "MOS update link"),
        (sdcard / "firmware.bin", "VDP update link"),
    ):
        _require_replaceable_link(path, label)

    if autoexec.is_symlink():
        raise SetupError(f"Refusing symlinked profile autoexec: {autoexec}")
    if autoexec.exists() and not autoexec.is_file():
        raise SetupError(f"Refusing non-file profile autoexec: {autoexec}")

    sources = stock_bin_files(inputs.shared_bin)
    if profile_bin.is_dir() and not profile_bin.is_symlink():
        for source in sources:
            destination = profile_bin / source.name
            if destination.is_symlink() or not destination.exists():
                continue
            if not destination.is_file():
                raise SetupError(
                    "Refusing non-file local /bin override: " f"{destination}"
                )
    return sources


def replace_symlink(link: Path, target: Path) -> None:
    """Refresh a managed symlink while refusing all real local paths."""

    if link.is_symlink():
        link.unlink()
    elif link.exists():
        raise SetupError(f"Refusing to replace non-symlink path: {link}")
    link.parent.mkdir(parents=True, exist_ok=True)
    relative_target = os.path.relpath(target, link.parent)
    link.symlink_to(relative_target, target_is_directory=target.is_dir())


def ensure_bin_overlay(profile_bin: Path) -> None:
    """Ensure /bin is local and writable, converting only an existing symlink."""

    if profile_bin.is_symlink():
        profile_bin.unlink()
    elif profile_bin.exists() and not profile_bin.is_dir():
        raise SetupError(f"Refusing non-directory /bin overlay: {profile_bin}")
    profile_bin.mkdir(parents=True, exist_ok=True)


def setup_profile(profile: Path, fab_root: Path) -> Path:
    """Create or refresh a stock profile and return its absolute path."""

    profile = absolute_path(profile)
    inputs = runtime_inputs(fab_root)
    sources = preflight_profile(profile, inputs)

    sdcard = profile / "sdcard"
    profile_bin = sdcard / "bin"
    agondev = sdcard / "agondev"
    profile.mkdir(parents=True, exist_ok=True)
    sdcard.mkdir(parents=True, exist_ok=True)
    ensure_bin_overlay(profile_bin)
    agondev.mkdir(parents=True, exist_ok=True)

    replace_symlink(profile / "fab-agon-emulator", inputs.executable)
    replace_symlink(profile / "firmware", inputs.firmware)
    replace_symlink(sdcard / "mos", inputs.shared_mos)
    replace_symlink(sdcard / "MOS.bin", inputs.update_mos)
    replace_symlink(sdcard / "firmware.bin", inputs.update_vdp)

    for source in sources:
        destination = profile_bin / source.name
        if destination.exists() and not destination.is_symlink():
            # A real profile-local file deliberately shadows the stock tool.
            continue
        replace_symlink(destination, source)

    autoexec = sdcard / "autoexec.txt"
    if not autoexec.exists():
        autoexec.write_bytes(DEFAULT_AUTOEXEC)

    return profile


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
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        profile = setup_profile(arguments.profile, arguments.fab_root)
        inputs = runtime_inputs(arguments.fab_root)
    except SetupError as error:
        print(f"setup_emulator.py: {error}", file=sys.stderr)
        return 1

    print(f"Emulator profile: {profile}")
    print(f"Fab executable:   {inputs.executable}")
    print(f"Stock MOS:        {inputs.mos}")
    print(f"Stock VDP:        {inputs.vdp}")
    print(f"Writable staging: {profile / 'sdcard/agondev'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
