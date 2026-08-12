#!/usr/bin/env python3
"""Read-only verification of the project-local development inputs."""

from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def git_commit(repository: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    expected_python_root = (ROOT / ".venv").resolve()
    executable = Path(sys.executable).absolute()
    require(
        Path(sys.prefix).resolve() == expected_python_root,
        f"Use the project interpreter, not {executable}",
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

    baseline = json.loads((ROOT / "evidence/baseline.json").read_text(encoding="utf-8"))
    require(
        git_commit(mos) == baseline["repositories"]["agon_mos"]["commit"],
        "The local agon-mos commit differs from the audited baseline",
    )
    # The installed link points at release/, while the evidence records its repo.
    require(
        git_commit(agondev.parent) == baseline["repositories"]["agondev"]["commit"],
        "The installed AgonDev commit differs from the audited baseline",
    )

    profile = ROOT / "emulator"
    fab_executable = profile / "fab-agon-emulator"
    stock_mos = profile / "firmware/mos_platform.bin"
    stock_vdp = profile / "firmware/vdp_platform.so"
    require(fab_executable.is_symlink(), "Run scripts/setup_emulator.py")
    require(stock_mos.is_file(), f"Missing stock Platform MOS: {stock_mos}")
    require(stock_vdp.is_file(), f"Missing stock Platform VDP: {stock_vdp}")
    expected_artifacts = baseline["stock_platform"]
    require(
        sha256(fab_executable) == expected_artifacts["fab_executable"]["sha256"],
        "Fab executable hash differs from the audited baseline",
    )
    require(
        sha256(stock_mos) == expected_artifacts["mos"]["sha256"],
        "Stock Platform MOS hash differs from the audited baseline",
    )
    require(
        sha256(stock_vdp) == expected_artifacts["vdp"]["sha256"],
        "Stock Platform VDP hash differs from the audited baseline",
    )

    help_result = subprocess.run(
        [str(fab_executable), "--help"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ).stdout
    require("default is platform" in help_result, "Fab help lacks Platform default")
    require("--sdcard <path>" in help_result, "Fab help lacks explicit SD-card option")
    dependencies = subprocess.run(
        ["ldd", str(fab_executable)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
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
