#!/usr/bin/env python3
"""Read-only verification of the project-local development inputs."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    expected_python_root = (ROOT / ".venv").resolve()
    executable = Path(sys.executable).absolute()
    require(
        Path(sys.prefix).resolve() == expected_python_root,
        f"Use the project interpreter, not {executable}",
    )
    require(
        sys.version_info >= (3, 14),
        f"Python 3.14 or newer is required, not {sys.version.split()[0]}",
    )

    agondev_link = ROOT / "toolchains/agondev"
    mos_link = ROOT / "upstream/agon-mos"
    require(agondev_link.is_symlink(), f"Missing setup link: {agondev_link}")
    require(mos_link.is_symlink(), f"Missing setup link: {mos_link}")
    agondev = agondev_link.resolve(strict=True)
    mos = mos_link.resolve(strict=True)

    for name in (
        "agondev-config",
        "ez80-none-elf-clang",
        "ez80-none-elf-as",
        "ez80-none-elf-ld",
        "ez80-none-elf-objcopy",
        "ez80-none-elf-objdump",
        "ez80-none-elf-readelf",
        "ez80-none-elf-size",
    ):
        require((agondev / "bin" / name).is_file(), f"Missing AgonDev tool: {name}")

    worktree = ROOT / "projects/mos-port/worktree"
    require((worktree / "main.c").is_file(), "Run scripts/prepare_mos_worktree.py")
    require((worktree / "src/defines.h").is_file(), "Incomplete MOS probe worktree")

    profile = ROOT / "emulator"
    fab_launcher = profile / "fab-agon-emulator"
    fab_executable = profile / "fab-agon-emulator.bin"
    stock_mos = profile / "firmware/mos_platform.bin"
    stock_vdp = profile / "firmware/vdp_platform.so"
    require(
        fab_launcher.is_file()
        and not fab_launcher.is_symlink()
        and os.access(fab_launcher, os.X_OK),
        "Run scripts/setup_emulator.py to create the generated direct launcher",
    )
    require(fab_executable.is_symlink(), "Run scripts/setup_emulator.py")
    require(
        fab_executable.is_file() and os.access(fab_executable, os.X_OK),
        f"Fab executable is missing or not executable: {fab_executable}",
    )
    require(stock_mos.is_file(), f"Missing stock Platform MOS: {stock_mos}")
    require(stock_vdp.is_file(), f"Missing stock Platform VDP: {stock_vdp}")

    runtime_environment = os.environ.copy()
    local_host_lib = Path("~").expanduser() / ".local" / "lib"
    if local_host_lib.is_dir():
        existing_library_path = runtime_environment.get("LD_LIBRARY_PATH")
        runtime_environment["LD_LIBRARY_PATH"] = str(local_host_lib) + (
            f":{existing_library_path}" if existing_library_path else ""
        )
    help_result = subprocess.run(
        [str(fab_executable), "--help"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=runtime_environment,
    ).stdout
    require("--firmware" in help_result, "Fab help lacks firmware selection")
    require("--sdcard <path>" in help_result, "Fab help lacks explicit SD-card option")
    ldd = shutil.which("ldd")
    if ldd:
        dependencies = subprocess.run(
            [ldd, str(fab_executable)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=runtime_environment,
        ).stdout
        require("not found" not in dependencies, "Fab has an unresolved shared library")

    print(f"Python:    {executable}")
    print(f"AgonDev:   {agondev}")
    print(f"agon-mos:  {mos}")
    print(f"worktree:  {worktree}")
    print(f"emulator:  {profile}")
    print("Environment verification passed")


if __name__ == "__main__":
    main()
