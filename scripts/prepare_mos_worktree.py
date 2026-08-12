#!/usr/bin/env python3
"""Copy tracked agon-mos files and apply validated initial-port edits.

The upstream worktree is read only. The destination must not exist, including
as a broken symlink. All edits are byte-oriented so source newline conventions
remain unchanged.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
from typing import Callable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

PATCHED_PATHS = (
    "src/defines.h",
    "main.c",
    "src/mos.c",
    "src/mos_editor.c",
    "src/clock.h",
    "src/timer.c",
    "src/uart.c",
    "src_fatfs/diskio.c",
    "src/mos_api.asm",
    "src/sd.asm",
    "src/vdp_protocol.asm",
)


class PreparationError(RuntimeError):
    """The source or destination did not satisfy a safe precondition."""


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _run_git(upstream: Path, arguments: Sequence[str]) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", os.fspath(upstream), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise PreparationError("git is required to prepare the MOS worktree") from exc
    if completed.returncode != 0:
        detail = os.fsdecode(completed.stderr).strip()
        raise PreparationError(
            f"git {' '.join(arguments)} failed: {detail or 'unknown error'}"
        )
    return completed.stdout


def _validate_upstream(path: Path) -> Path:
    try:
        upstream = path.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise PreparationError(f"upstream checkout does not exist: {path}") from exc
    if not upstream.is_dir():
        raise PreparationError(f"upstream checkout is not a directory: {upstream}")

    reported_raw = _run_git(upstream, ("rev-parse", "--show-toplevel"))
    reported = Path(os.fsdecode(reported_raw).strip()).resolve(strict=True)
    if reported != upstream:
        raise PreparationError(
            f"upstream path must be the Git worktree root (reported {reported})"
        )
    return upstream


def _safe_tracked_paths(upstream: Path) -> list[PurePosixPath]:
    output = _run_git(upstream, ("ls-files", "--cached", "-z", "--"))
    names = output.split(b"\0")
    if names and names[-1] == b"":
        names.pop()
    if not names:
        raise PreparationError("upstream Git index has no tracked files")

    result: list[PurePosixPath] = []
    seen: set[str] = set()
    for raw_name in names:
        name = os.fsdecode(raw_name)
        relative = PurePosixPath(name)
        if (
            not name
            or relative.is_absolute()
            or any(part in ("", ".", "..") for part in relative.parts)
        ):
            raise PreparationError(f"unsafe tracked path from Git index: {name!r}")
        normalized = relative.as_posix()
        if normalized in seen:
            raise PreparationError(f"duplicate tracked path from Git index: {name!r}")
        seen.add(normalized)

        cursor = upstream
        for index, part in enumerate(relative.parts):
            cursor /= part
            try:
                metadata = cursor.lstat()
            except FileNotFoundError as exc:
                raise PreparationError(f"tracked path is missing: {relative}") from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise PreparationError(
                    f"refusing to follow tracked symbolic link: {relative}"
                )
            if index < len(relative.parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
                raise PreparationError(f"tracked path has a non-directory parent: {relative}")
        if not stat.S_ISREG(metadata.st_mode):
            raise PreparationError(f"tracked path is not a regular file: {relative}")
        try:
            cursor.resolve(strict=True).relative_to(upstream)
        except ValueError as exc:
            raise PreparationError(f"tracked path escapes upstream: {relative}") from exc
        result.append(relative)

    return sorted(result, key=PurePosixPath.as_posix)


def _replace_exact(
    data: bytes,
    old: bytes,
    new: bytes,
    expected: int,
    description: str,
) -> bytes:
    old_count = data.count(old)
    new_count = data.count(new)
    if old_count != expected or new_count != 0:
        raise PreparationError(
            f"{description}: expected {expected} old and 0 new forms, "
            f"found {old_count} old and {new_count} new"
        )
    result = data.replace(old, new)
    if result.count(old) != 0 or result.count(new) != expected:
        raise PreparationError(f"{description}: replacement verification failed")
    return result


def _patch_defines(data: bytes) -> bytes:
    symbols = (
        b"_heapbot",
        b"_heaptop",
        b"_stack",
        b"_low_data",
        b"_low_bss",
        b"_low_romdata",
    )
    result = data
    for symbol in symbols:
        result = _replace_exact(
            result,
            b"extern void " + symbol + b"[];",
            b"extern unsigned char " + symbol + b"[];",
            1,
            f"src/defines.h {os.fsdecode(symbol)} declaration",
        )
    return result


def _patch_main(data: bytes) -> bytes:
    newline = _uniform_newline(data, "main.c portability edits")
    result = _replace_exact(
        data,
        b"#include <eZ80.h>",
        b"#include <ez80.h>",
        1,
        "main.c eZ80 include casing",
    )
    result = _replace_exact(
        result,
        b"#include <CTYPE.h>",
        b"#include <ctype.h>",
        1,
        "main.c ctype include casing",
    )
    result = _replace_exact(
        result,
        b"#include <String.h>",
        b"#include <string.h>",
        1,
        "main.c string include casing",
    )
    old_quickrand = (
        b"int quickrand(void) {"
        + newline
        + b'\tasm("ld a,r\\n"'
        + newline
        + b'\t\t"ld hl,0\\n"'
        + newline
        + b'\t\t"ld l,a\\n");'
        + newline
        + b"}"
    )
    new_quickrand = (
        b"int quickrand(void) {"
        + newline
        + b"#ifdef AGONDEV"
        + newline
        + b"\tunsigned char value;"
        + newline
        + b'\t__asm__ volatile ("ld a,r" : "=a"(value) : : "cc");'
        + newline
        + b"\treturn value;"
        + newline
        + b"#else"
        + newline
        + b'\tasm("ld a,r\\n"'
        + newline
        + b'\t\t"ld hl,0\\n"'
        + newline
        + b'\t\t"ld l,a\\n");'
        + newline
        + b"#endif"
        + newline
        + b"}"
    )
    result = _replace_exact(
        result,
        old_quickrand,
        new_quickrand,
        1,
        "main.c quickrand explicit AgonDev return",
    )
    return _replace_exact(
        result,
        b"extern void _heapbot[];",
        b"extern unsigned char _heapbot[];",
        1,
        "main.c _heapbot declaration",
    )


def _patch_mos(data: bytes) -> bytes:
    result = _replace_exact(
        data,
        b"#include <eZ80.h>",
        b"#include <ez80.h>",
        1,
        "src/mos.c eZ80 include casing",
    )
    return _replace_exact(
        result,
        b"extern void sysvars[];",
        b"extern unsigned char sysvars[];",
        1,
        "src/mos.c sysvars declaration",
    )


def _patch_ez80_include_casing(data: bytes, description: str) -> bytes:
    return _replace_exact(
        data,
        b"#include <eZ80.h>",
        b"#include <ez80.h>",
        1,
        description,
    )


def _patch_mos_editor(data: bytes) -> bytes:
    return _patch_ez80_include_casing(
        data, "src/mos_editor.c eZ80 include casing"
    )


def _patch_timer(data: bytes) -> bytes:
    return _patch_ez80_include_casing(data, "src/timer.c eZ80 include casing")


def _patch_uart(data: bytes) -> bytes:
    return _patch_ez80_include_casing(data, "src/uart.c eZ80 include casing")


def _uniform_newline(data: bytes, description: str) -> bytes:
    line_feeds = data.count(b"\n")
    crlf = data.count(b"\r\n")
    if line_feeds == 0:
        raise PreparationError(f"{description}: file has no recognizable newlines")
    if crlf == line_feeds:
        return b"\r\n"
    if crlf == 0:
        return b"\n"
    raise PreparationError(f"{description}: mixed line endings are not patched implicitly")


def _patch_clock(data: bytes) -> bytes:
    newline = _uniform_newline(data, "src/clock.h include")
    old = b"#define RTC_H" + newline + newline + b"#define EPOCH_YEAR"
    new = (
        b"#define RTC_H"
        + newline
        + newline
        + b"#include <defines.h>"
        + newline
        + newline
        + b"#define EPOCH_YEAR"
    )
    return _replace_exact(data, old, new, 1, "src/clock.h include")


def _patch_diskio(data: bytes) -> bytes:
    return _replace_exact(
        data,
        b"yr =  (tstruct.year - EPOCH_YEAR) << 25;",
        b"yr =  (DWORD)(tstruct.year - EPOCH_YEAR) << 25;",
        1,
        "src_fatfs/diskio.c DWORD shift",
    )


def _patch_long_branch(
    data: bytes, old_instruction: bytes, new_instruction: bytes, description: str
) -> bytes:
    """Make a ZDS-relaxed branch explicit for GNU as.

    ZDS silently emits a long conditional jump for these out-of-range JR
    instructions.  GNU as diagnoses the range instead.  An explicit JP is
    valid in both dialects and makes the maintained intent visible.
    """

    return _replace_exact(data, old_instruction, new_instruction, 1, description)


def _patch_mos_api_asm(data: bytes) -> bytes:
    return _patch_long_branch(
        data,
        b"\t\t\tJR\tNC, $F\t\t\t; Yes, so jump to next block",
        b"\t\t\tJP\tNC, $F\t\t\t; Yes, so jump to next block",
        "src/mos_api.asm out-of-range FatFS dispatch branch",
    )


def _patch_sd_asm(data: bytes) -> bytes:
    newline = _uniform_newline(data, "src/sd.asm long branch")
    return _patch_long_branch(
        data,
        b"\t\tPUSH\t\tAF\t\t; Save res1 to be returned"
        + newline
        + b"\t\tCP\t\tA,SD_READY"
        + newline
        + b"\t\tJR\t\tNZ,$out3",
        b"\t\tPUSH\t\tAF\t\t; Save res1 to be returned"
        + newline
        + b"\t\tCP\t\tA,SD_READY"
        + newline
        + b"\t\tJP\t\tNZ,$out3",
        "src/sd.asm out-of-range write-error branch",
    )


def _patch_vdp_protocol_asm(data: bytes) -> bytes:
    return _patch_long_branch(
        data,
        b"\t\t\tJR\tZ, vdp_protocol_state3",
        b"\t\t\tJP\tZ, vdp_protocol_state3",
        "src/vdp_protocol.asm out-of-range state branch",
    )


PATCHERS: dict[str, Callable[[bytes], bytes]] = {
    "src/defines.h": _patch_defines,
    "main.c": _patch_main,
    "src/mos.c": _patch_mos,
    "src/mos_editor.c": _patch_mos_editor,
    "src/clock.h": _patch_clock,
    "src/timer.c": _patch_timer,
    "src/uart.c": _patch_uart,
    "src_fatfs/diskio.c": _patch_diskio,
    "src/mos_api.asm": _patch_mos_api_asm,
    "src/sd.asm": _patch_sd_asm,
    "src/vdp_protocol.asm": _patch_vdp_protocol_asm,
}


def _validated_patch_bytes(upstream: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for relative_name in PATCHED_PATHS:
        source = upstream.joinpath(*PurePosixPath(relative_name).parts)
        if not source.is_file() or source.is_symlink():
            raise PreparationError(f"required patch source is not a regular file: {relative_name}")
        result[relative_name] = PATCHERS[relative_name](source.read_bytes())
    return result


def _absolute_from_root(repository_root: Path, value: Path) -> Path:
    expanded = value.expanduser()
    if not expanded.is_absolute():
        expanded = repository_root / expanded
    return Path(os.path.abspath(os.fspath(expanded)))


def _safe_destination_parent(repository_root: Path, parent: Path) -> None:
    try:
        relative = parent.relative_to(repository_root)
    except ValueError as exc:
        raise PreparationError(
            f"destination must remain inside repository root: {parent}"
        ) from exc

    cursor = repository_root
    for part in relative.parts:
        cursor /= part
        if _lexists(cursor):
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise PreparationError(f"destination parent is not a real directory: {cursor}")
        else:
            cursor.mkdir(mode=0o755)


def prepare_worktree(
    repository_root: Path,
    upstream: Path,
    destination: Path,
) -> int:
    """Copy every tracked regular file and apply the validated patch groups."""

    try:
        repository_root = repository_root.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise PreparationError(f"repository root does not exist: {repository_root}") from exc
    if not repository_root.is_dir():
        raise PreparationError(f"repository root is not a directory: {repository_root}")

    upstream = _validate_upstream(upstream)
    destination = _absolute_from_root(repository_root, destination)
    if destination == repository_root:
        raise PreparationError("destination cannot be the repository root")
    try:
        destination.relative_to(repository_root)
    except ValueError as exc:
        raise PreparationError(
            f"destination must remain inside repository root: {destination}"
        ) from exc
    if _lexists(destination):
        raise PreparationError(f"refusing to replace existing destination: {destination}")

    tracked = _safe_tracked_paths(upstream)
    tracked_names = {path.as_posix() for path in tracked}
    missing_patch_sources = sorted(set(PATCHED_PATHS) - tracked_names)
    if missing_patch_sources:
        raise PreparationError(
            "required patch files are not tracked: " + ", ".join(missing_patch_sources)
        )
    patched_bytes = _validated_patch_bytes(upstream)

    _safe_destination_parent(repository_root, destination.parent)
    try:
        destination.mkdir(mode=0o755)
    except FileExistsError as exc:
        raise PreparationError(
            f"refusing to replace existing destination: {destination}"
        ) from exc

    try:
        for relative in tracked:
            source = upstream.joinpath(*relative.parts)
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            relative_name = relative.as_posix()
            if relative_name in patched_bytes:
                target.write_bytes(patched_bytes[relative_name])
                shutil.copystat(source, target, follow_symlinks=False)
            else:
                shutil.copy2(source, target, follow_symlinks=False)
    except Exception as exc:
        raise PreparationError(
            f"copy failed; partial destination retained at {destination}: {exc}"
        ) from exc

    for relative_name, expected in patched_bytes.items():
        actual = destination.joinpath(*PurePosixPath(relative_name).parts).read_bytes()
        if actual != expected:
            raise PreparationError(f"post-copy verification failed: {relative_name}")
    return len(tracked)


def check_worktree(
    repository_root: Path,
    upstream: Path,
    destination: Path,
) -> int:
    """Verify that an existing destination exactly matches a prepared copy."""

    try:
        repository_root = repository_root.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise PreparationError(f"repository root does not exist: {repository_root}") from exc
    if not repository_root.is_dir():
        raise PreparationError(f"repository root is not a directory: {repository_root}")

    upstream = _validate_upstream(upstream)
    destination = _absolute_from_root(repository_root, destination)
    try:
        destination.relative_to(repository_root)
    except ValueError as exc:
        raise PreparationError(
            f"destination must remain inside repository root: {destination}"
        ) from exc
    if not destination.is_dir() or destination.is_symlink():
        raise PreparationError(f"destination is not a real directory: {destination}")

    tracked = _safe_tracked_paths(upstream)
    tracked_names = {path.as_posix() for path in tracked}
    missing_patch_sources = sorted(set(PATCHED_PATHS) - tracked_names)
    if missing_patch_sources:
        raise PreparationError(
            "required patch files are not tracked: " + ", ".join(missing_patch_sources)
        )
    patched_bytes = _validated_patch_bytes(upstream)

    actual_names: set[str] = set()
    for path in sorted(destination.rglob("*")):
        relative_name = path.relative_to(destination).as_posix()
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise PreparationError(f"destination contains symbolic link: {relative_name}")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise PreparationError(f"destination contains non-regular file: {relative_name}")
        actual_names.add(relative_name)

    missing = sorted(tracked_names - actual_names)
    extra = sorted(actual_names - tracked_names)
    if missing:
        raise PreparationError("destination is missing tracked files: " + ", ".join(missing))
    if extra:
        raise PreparationError("destination contains extra files: " + ", ".join(extra))

    for relative in tracked:
        relative_name = relative.as_posix()
        source = upstream.joinpath(*relative.parts)
        target = destination.joinpath(*relative.parts)
        expected = patched_bytes.get(relative_name)
        if expected is None:
            expected = source.read_bytes()
        if target.read_bytes() != expected:
            raise PreparationError(f"destination content differs: {relative_name}")
        expected_mode = stat.S_IMODE(source.stat().st_mode) & 0o111
        actual_mode = stat.S_IMODE(target.stat().st_mode) & 0o111
        if actual_mode != expected_mode:
            raise PreparationError(
                f"destination executable mode differs: {relative_name} "
                f"(expected {expected_mode:o}, found {actual_mode:o})"
            )
    return len(tracked)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        "--root",
        dest="repository_root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository root (default: script parent)",
    )
    parser.add_argument(
        "--upstream",
        "--source",
        dest="upstream",
        type=Path,
        help="agon-mos worktree (default: upstream/agon-mos link)",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        help="copy destination (default: projects/mos-port/worktree)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify an existing destination without changing it",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repository_root = args.repository_root.expanduser().resolve(strict=True)
        upstream = args.upstream or repository_root / "upstream" / "agon-mos"
        if not upstream.is_absolute():
            upstream = repository_root / upstream
        destination = args.destination or Path("projects/mos-port/worktree")
        if args.check:
            count = check_worktree(repository_root, upstream, destination)
        else:
            count = prepare_worktree(repository_root, upstream, destination)
    except (OSError, PreparationError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output = _absolute_from_root(repository_root, destination)
    action = "verified" if args.check else "prepared"
    print(f"{action} {count} tracked files at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
