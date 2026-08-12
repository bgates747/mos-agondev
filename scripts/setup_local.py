#!/usr/bin/env python3
"""Create the two local, deliberately untracked source links used by this repo.

Defaults are resolved from the repository root. Path overrides support
isolated tests and alternate checkout layouts.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AGONDEV_SOURCE = Path("../../agondev")
DEFAULT_MOS_SOURCE = Path("../../agon-mos")

EXPECTED_AGONDEV_TOOLS = (
    "release/bin/agondev-config",
    "release/bin/ez80-none-elf-clang",
    "release/bin/ez80-none-elf-as",
    "release/bin/ez80-none-elf-ld",
    "release/bin/ez80-none-elf-objcopy",
    "release/bin/ez80-none-elf-objdump",
    "release/bin/ez80-none-elf-readelf",
    "release/bin/ez80-none-elf-size",
    "release/bin/ez80-none-elf-nm",
)

EXPECTED_MOS_FILES = (
    "MOS.zdsproj",
    "main.c",
    "src/defines.h",
    "src/mos.c",
    "src/clock.h",
    "src_fatfs/diskio.c",
)


class SetupError(RuntimeError):
    """A validation or safe-creation precondition failed."""


def _lexists(path: Path) -> bool:
    """Like Path.exists(), but also report a broken symbolic link."""

    return os.path.lexists(os.fspath(path))


def _existing_directory(path: Path, description: str) -> Path:
    expanded = path.expanduser()
    try:
        resolved = expanded.resolve(strict=True)
    except FileNotFoundError as exc:
        raise SetupError(f"{description} does not exist: {expanded}") from exc
    if not resolved.is_dir():
        raise SetupError(f"{description} is not a directory: {resolved}")
    return resolved


def _path_from_root(repository_root: Path, value: Path) -> Path:
    value = value.expanduser()
    return value if value.is_absolute() else repository_root / value


def validate_agondev(source: Path) -> Path:
    """Validate an AgonDev checkout and return its install-style release root."""

    source = _existing_directory(source, "AgonDev checkout")
    missing: list[str] = []
    non_executable: list[str] = []
    for relative_name in EXPECTED_AGONDEV_TOOLS:
        candidate = source / relative_name
        if not candidate.is_file():
            missing.append(relative_name)
        elif not os.access(candidate, os.X_OK):
            non_executable.append(relative_name)
    if missing:
        raise SetupError(
            "AgonDev checkout is missing expected tools: " + ", ".join(missing)
        )
    if non_executable:
        raise SetupError(
            "AgonDev tools are not executable: " + ", ".join(non_executable)
        )
    return source / "release"


def _git_toplevel(source: Path) -> Path:
    try:
        completed = subprocess.run(
            ["git", "-C", os.fspath(source), "rev-parse", "--show-toplevel"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SetupError("git is required to validate the agon-mos checkout") from exc
    if completed.returncode != 0:
        detail = os.fsdecode(completed.stderr).strip()
        raise SetupError(f"agon-mos source is not a Git worktree: {detail or source}")
    reported = Path(os.fsdecode(completed.stdout).strip()).resolve(strict=True)
    return reported


def validate_mos(source: Path) -> Path:
    source = _existing_directory(source, "agon-mos checkout")
    reported = _git_toplevel(source)
    if reported != source:
        raise SetupError(
            f"agon-mos path must be the worktree root (reported {reported}, got {source})"
        )
    missing = [name for name in EXPECTED_MOS_FILES if not (source / name).is_file()]
    if missing:
        raise SetupError(
            "agon-mos checkout is missing expected files: " + ", ".join(missing)
        )
    return source


def _validate_link_parent(parent: Path) -> None:
    if not _lexists(parent):
        return
    metadata = parent.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SetupError(f"link parent must be a real directory: {parent}")


def create_local_links(
    repository_root: Path,
    agondev_source: Path,
    mos_source: Path,
) -> tuple[Path, Path]:
    """Validate both sources, then create exactly two relative symlinks.

    All collision checks happen before either link is created. An existing
    relative symlink to the validated target is accepted, making setup safe to
    rerun; every other existing path is refused. If a later race still makes
    creation fail, only links created by this call are rolled back.
    """

    repository_root = _existing_directory(repository_root, "repository root")
    agondev_release = validate_agondev(agondev_source)
    mos_source = validate_mos(mos_source)

    specifications = (
        (repository_root / "toolchains" / "agondev", agondev_release),
        (repository_root / "upstream" / "agon-mos", mos_source),
    )

    for link, _source in specifications:
        _validate_link_parent(link.parent)
        if _lexists(link):
            if not link.is_symlink():
                raise SetupError(f"refusing to replace existing path: {link}")
            raw_target = os.readlink(link)
            try:
                resolved_target = link.resolve(strict=True)
            except (FileNotFoundError, RuntimeError) as exc:
                raise SetupError(f"refusing broken local link: {link}") from exc
            if os.path.isabs(raw_target) or resolved_target != _source:
                raise SetupError(f"refusing unexpected local link: {link}")

    for link, _source in specifications:
        if not _lexists(link.parent):
            link.parent.mkdir(mode=0o755)

    created: list[tuple[Path, str]] = []
    try:
        for link, source in specifications:
            if _lexists(link):
                continue
            relative_target = os.path.relpath(source, start=link.parent)
            if os.path.isabs(relative_target):
                raise SetupError(f"could not form a relative target for {link}")
            link.symlink_to(relative_target, target_is_directory=True)
            created.append((link, relative_target))
            if link.resolve(strict=True) != source:
                raise SetupError(f"created link does not resolve to validated source: {link}")
    except Exception:
        for link, expected_text in reversed(created):
            try:
                if link.is_symlink() and os.readlink(link) == expected_text:
                    link.unlink()
            except OSError:
                pass
        raise

    return specifications[0][0], specifications[1][0]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        "--root",
        dest="repository_root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository receiving toolchains/ and upstream/ (default: script parent)",
    )
    parser.add_argument(
        "--agondev",
        "--agondev-source",
        dest="agondev_source",
        type=Path,
        help="AgonDev checkout (default: ../../agondev from repository root)",
    )
    parser.add_argument(
        "--agon-mos",
        "--mos-source",
        dest="mos_source",
        type=Path,
        help="agon-mos checkout (default: ../../agon-mos from repository root)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repository_root = _existing_directory(args.repository_root, "repository root")
        agondev_source = _path_from_root(
            repository_root,
            args.agondev_source or DEFAULT_AGONDEV_SOURCE,
        )
        mos_source = _path_from_root(
            repository_root,
            args.mos_source or DEFAULT_MOS_SOURCE,
        )
        agondev_link, mos_link = create_local_links(
            repository_root, agondev_source, mos_source
        )
    except (OSError, SetupError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"configured {agondev_link} -> {os.readlink(agondev_link)}")
    print(f"configured {mos_link} -> {os.readlink(mos_link)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
