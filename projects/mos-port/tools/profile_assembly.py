#!/usr/bin/env python3
"""Validate one exact, source-owned assembly link composition."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Iterable


class AssemblyProfileError(ValueError):
    pass


def _relative_name(name: str, suffix: str, kind: str) -> str:
    relative = PurePosixPath(name)
    canonical = relative.as_posix()
    if (
        not name
        or "\\" in name
        or relative.is_absolute()
        or ".." in relative.parts
        or canonical != name
        or relative.suffix != suffix
        or not relative.parts
        or relative.parts[0] not in {"src", "src_startup"}
    ):
        raise AssemblyProfileError(f"unsafe configured assembly {kind}: {name!r}")
    return canonical


def validate_assembly_composition(
    source_root: Path,
    source_names: Iterable[str],
    object_names: Iterable[str],
) -> dict[str, Path]:
    """Return declared sources after validating the exact source/object map."""
    root = source_root.resolve(strict=True)
    if not root.is_dir():
        raise AssemblyProfileError(f"assembly source root is not a directory: {root}")

    sources: dict[str, Path] = {}
    for raw_name in source_names:
        name = _relative_name(raw_name, ".asm", "source path")
        if name in sources:
            raise AssemblyProfileError(
                f"duplicate configured assembly source path: {name}"
            )
        lexical = root / Path(*PurePosixPath(name).parts)
        try:
            resolved = lexical.resolve(strict=True)
        except FileNotFoundError:
            raise AssemblyProfileError(
                f"configured assembly source is missing: {name}"
            ) from None
        try:
            resolved.relative_to(root)
        except ValueError:
            raise AssemblyProfileError(
                f"configured assembly source escapes through a symlink: {name}"
            ) from None
        if not resolved.is_file():
            raise AssemblyProfileError(
                f"configured assembly source is not a file: {name}"
            )
        sources[name] = lexical

    objects: set[str] = set()
    for raw_name in object_names:
        name = _relative_name(raw_name, ".o", "object path")
        if name in objects:
            raise AssemblyProfileError(
                f"duplicate configured assembly object path: {name}"
            )
        objects.add(name)

    expected = {
        PurePosixPath(name).with_suffix(".o").as_posix() for name in sources
    }
    if objects != expected:
        raise AssemblyProfileError(
            "configured assembly objects differ from the exact source mapping: "
            f"expected {sorted(expected)}, got {sorted(objects)}"
        )
    return sources


def validate_object_destinations(
    build_root: Path, object_root: Path, object_names: Iterable[str]
) -> list[Path]:
    """Reject output roots or parents that could redirect assembler writes."""
    root = build_root.resolve(strict=True)
    if not root.is_dir():
        raise AssemblyProfileError(f"build root is not a directory: {root}")
    raw_object_root = object_root
    if raw_object_root.is_absolute():
        try:
            relative_root = raw_object_root.relative_to(root)
        except ValueError as error:
            raise AssemblyProfileError(
                f"assembly object root is outside the build root: {object_root}"
            ) from error
    else:
        relative_root = raw_object_root
    pure_root = PurePosixPath(relative_root.as_posix())
    if (
        not pure_root.parts
        or any(part in ("", ".", "..") for part in pure_root.parts)
        or "\\" in relative_root.as_posix()
    ):
        raise AssemblyProfileError(
            f"unsafe assembly object root: {object_root}"
        )

    def check_parent_chain(relative: PurePosixPath) -> None:
        cursor = root
        for part in relative.parts:
            cursor /= part
            if not os.path.lexists(cursor):
                continue
            metadata = cursor.lstat()
            if cursor.is_symlink():
                raise AssemblyProfileError(
                    f"assembly object destination traverses a symlink: {cursor}"
                )
            if not cursor.is_dir():
                raise AssemblyProfileError(
                    f"assembly object destination parent is not a directory: {cursor}"
                )

    check_parent_chain(pure_root)
    destinations: list[Path] = []
    for raw_name in object_names:
        name = _relative_name(raw_name, ".o", "object path")
        relative = pure_root.joinpath(*PurePosixPath(name).parts)
        check_parent_chain(relative.parent)
        destination = root.joinpath(*relative.parts)
        if os.path.lexists(destination) and destination.is_symlink():
            raise AssemblyProfileError(
                f"assembly object destination is a symlink: {destination}"
            )
        destinations.append(destination)
    return destinations


def resolve_linked_objects(object_root: Path, object_names: Iterable[str]) -> list[Path]:
    """Resolve an already-built exact assembly object list inside its root."""
    if object_root.is_symlink():
        raise AssemblyProfileError(
            f"assembly object root must not be a symlink: {object_root}"
        )
    root = object_root.resolve(strict=True)
    if not root.is_dir():
        raise AssemblyProfileError(f"assembly object root is not a directory: {root}")
    result: list[Path] = []
    for raw_name in object_names:
        name = _relative_name(raw_name, ".o", "object path")
        lexical = root / Path(*PurePosixPath(name).parts)
        try:
            resolved = lexical.resolve(strict=True)
        except FileNotFoundError:
            raise AssemblyProfileError(
                f"configured linked assembly object is missing: {name}"
            ) from None
        try:
            resolved.relative_to(root)
        except ValueError:
            raise AssemblyProfileError(
                f"configured linked assembly object escapes through a symlink: {name}"
            ) from None
        if not resolved.is_file():
            raise AssemblyProfileError(
                f"configured linked assembly object is not a file: {name}"
            )
        result.append(lexical)
    return result


def exports_from_sources(sources: Iterable[Path]) -> set[str]:
    exports: set[str] = set()
    for source in sources:
        for raw_line in source.read_text(encoding="utf-8", errors="strict").splitlines():
            code = raw_line.split(";", 1)[0]
            match = re.search(r"\bXDEF\b(.*)$", code, flags=re.IGNORECASE)
            if match is not None:
                exports.update(
                    re.findall(r"[A-Za-z_.][A-Za-z0-9_.$]*", match.group(1))
                )
    return exports


def select_linked_sources(
    linked_sources: dict[str, Path], selected_names: Iterable[str]
) -> list[Path]:
    """Select a duplicate-free subset; undeclared XDEF permission is invalid."""
    names = list(selected_names)
    if len(names) != len(set(names)):
        raise AssemblyProfileError(
            "duplicate configured profile assembly source path"
        )
    undeclared = set(names) - set(linked_sources)
    if undeclared:
        raise AssemblyProfileError(
            "profile assembly permission names an unlinked source: "
            f"{sorted(undeclared)}"
        )
    return [linked_sources[name] for name in names]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--build-root", default=Path.cwd(), type=Path)
    parser.add_argument("--object-root", required=True, type=Path)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--object", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        sources = validate_assembly_composition(
            args.source_root, args.source, args.object
        )
        validate_object_destinations(
            args.build_root, args.object_root, args.object
        )
    except (AssemblyProfileError, FileNotFoundError) as error:
        print(f"assembly profile invalid: {error}", file=sys.stderr)
        return 1
    print(f"assembly profile verified: {len(sources)} exact source/object pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
