#!/usr/bin/env python3
"""Run GNU as on generated MOS source and remap diagnostics to ZDS input."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Sequence


MANIFEST_SCHEMA = 2
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class MappingError(ValueError):
    """The generated source and its sidecar manifest are not trustworthy."""


def _regular_file(path: Path, description: str) -> Path:
    if path.is_symlink():
        raise MappingError(f"{description} must not be a symbolic link: {path}")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as error:
        raise MappingError(f"{description} does not exist: {path}") from error
    if not resolved.is_file():
        raise MappingError(f"{description} is not a regular file: {path}")
    return resolved


def _safe_relative_name(value: object, description: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise MappingError(f"{description} must be a non-empty POSIX relative path")
    if any(ord(character) < 32 or character == ":" for character in value):
        raise MappingError(f"{description} contains an unsafe character: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise MappingError(f"{description} is not a normalized relative path: {value!r}")
    return value


def load_mapping(manifest_path: Path, source_path: Path) -> tuple[str, tuple[tuple[str, int], ...]]:
    """Validate and return the maintained root plus one mapping per generated line."""

    manifest = _regular_file(manifest_path, "mapping manifest")
    source = _regular_file(source_path, "generated assembly source")
    output_root = manifest.parent.resolve(strict=True)
    try:
        relative_source = source.relative_to(output_root).as_posix()
    except ValueError as error:
        raise MappingError(
            f"generated source must be inside the manifest directory: {source}"
        ) from error

    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MappingError(f"cannot read mapping manifest {manifest}: {error}") from error
    if not isinstance(document, dict) or document.get("schema") != MANIFEST_SCHEMA:
        raise MappingError(
            f"mapping manifest schema must be {MANIFEST_SCHEMA}: {manifest}"
        )
    files = document.get("files")
    if not isinstance(files, list):
        raise MappingError("mapping manifest 'files' must be a list")

    selected: dict[str, object] | None = None
    seen_outputs: set[str] = set()
    for ordinal, raw_entry in enumerate(files):
        if not isinstance(raw_entry, dict):
            raise MappingError(f"mapping manifest file entry {ordinal} must be an object")
        output_name = _safe_relative_name(
            raw_entry.get("output"), f"mapping manifest file entry {ordinal} output"
        )
        if output_name in seen_outputs:
            raise MappingError(f"duplicate generated output in mapping manifest: {output_name}")
        seen_outputs.add(output_name)
        if output_name == relative_source:
            selected = raw_entry
    if selected is None:
        raise MappingError(f"generated source is absent from mapping manifest: {relative_source}")

    maintained_root = _safe_relative_name(selected.get("source"), "maintained source name")
    expected_hash = selected.get("output_sha256")
    if not isinstance(expected_hash, str) or SHA256_RE.fullmatch(expected_hash) is None:
        raise MappingError(f"invalid generated-source SHA-256 for {relative_source}")
    try:
        source_bytes = source.read_bytes()
        source_text = source_bytes.decode("utf-8")
    except OSError as error:
        raise MappingError(f"cannot read generated source {source}: {error}") from error
    except UnicodeError as error:
        raise MappingError(f"generated source is not UTF-8: {relative_source}") from error
    actual_hash = hashlib.sha256(source_bytes).hexdigest()
    if actual_hash != expected_hash:
        raise MappingError(
            f"generated source is stale or modified: {relative_source} "
            f"(expected {expected_hash}, found {actual_hash})"
        )

    raw_locations = selected.get("output_locations")
    if not isinstance(raw_locations, list):
        raise MappingError(f"output location map for {relative_source} must be a list")
    source_line_count = len(source_text.splitlines())
    if len(raw_locations) != source_line_count:
        raise MappingError(
            f"output location map for {relative_source} has {len(raw_locations)} entries, "
            f"but generated source has {source_line_count} lines"
        )

    locations: list[tuple[str, int]] = []
    for line_number, raw_location in enumerate(raw_locations, 1):
        if not isinstance(raw_location, dict):
            raise MappingError(
                f"output location {line_number} for {relative_source} must be an object"
            )
        original_source = _safe_relative_name(
            raw_location.get("source"),
            f"original source at generated line {line_number}",
        )
        original_line = raw_location.get("line")
        if isinstance(original_line, bool) or not isinstance(original_line, int) or original_line < 1:
            raise MappingError(
                f"original line at generated line {line_number} must be a positive integer"
            )
        locations.append((original_source, original_line))
    return maintained_root, tuple(locations)


def remap_diagnostics(
    diagnostics: bytes,
    generated_source: Path,
    maintained_root: str,
    locations: Sequence[tuple[str, int]],
) -> bytes:
    """Rewrite only exact GNU-as references to the generated input path."""

    generated = os.fsencode(str(generated_source.resolve(strict=False)))
    root = maintained_root.encode("utf-8")
    output: list[bytes] = []
    for physical in diagnostics.splitlines(keepends=True):
        body = physical.rstrip(b"\r\n")
        newline = physical[len(body):]
        prefix = generated + b":"
        if not body.startswith(prefix):
            output.append(physical)
            continue
        remainder = body[len(prefix):]
        match = re.match(rb"(?P<line>[1-9][0-9]*)(?P<tail>:.*)$", remainder)
        if match is None:
            if remainder == b" Assembler messages:":
                output.append(root + b":" + remainder + newline)
            else:
                output.append(physical)
            continue
        generated_line = int(match.group("line"))
        if generated_line > len(locations):
            output.append(physical)
            continue
        original_source, original_line = locations[generated_line - 1]
        output.append(
            original_source.encode("utf-8")
            + b":"
            + str(original_line).encode("ascii")
            + match.group("tail")
            + newline
        )
    return b"".join(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--assembler", required=True, type=Path)
    parser.add_argument(
        "assembler_args",
        nargs=argparse.REMAINDER,
        help="GNU-as arguments after '--'; the generated source is appended",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assembler_args = list(args.assembler_args)
    if assembler_args[:1] == ["--"]:
        assembler_args.pop(0)
    try:
        assembler = _regular_file(args.assembler, "assembler executable")
        if not os.access(assembler, os.X_OK):
            raise MappingError(f"assembler is not executable: {assembler}")
        source = _regular_file(args.source, "generated assembly source")
        maintained_root, locations = load_mapping(args.manifest, source)
        completed = subprocess.run(
            [assembler, *assembler_args, source],
            check=False,
            stderr=subprocess.PIPE,
        )
        assert completed.stderr is not None
        sys.stderr.buffer.write(
            remap_diagnostics(completed.stderr, source, maintained_root, locations)
        )
        sys.stderr.buffer.flush()
        return completed.returncode
    except (MappingError, OSError) as error:
        print(f"assemble_zds: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
