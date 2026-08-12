#!/usr/bin/env python3
"""Build a restricted MOS firmware runtime archive from an explicit allow-list."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def allowed_members(policy: dict[str, object]) -> list[str]:
    result: list[str] = []
    for category, members in policy["allowed_archive_members"].items():
        for member in members:
            if not re.fullmatch(r"[A-Za-z0-9_.+-]+\.o", member):
                raise ValueError(f"unsafe archive member in {category}: {member!r}")
            if member in result:
                raise ValueError(f"duplicate allow-listed archive member: {member}")
            result.append(member)
    return result


def build(
    ar: Path,
    source_archive: Path,
    local_objects: list[Path],
    output: Path,
    policy: dict[str, object],
) -> list[str]:
    actual_hash = sha256(source_archive)
    if actual_hash != policy["archive_sha256"]:
        raise ValueError(
            f"source archive hash mismatch: expected {policy['archive_sha256']}, "
            f"got {actual_hash}"
        )

    members = allowed_members(policy)
    expected = [path.name for path in local_objects] + members
    if len(expected) != len(set(expected)):
        raise ValueError("local and allow-listed archive member names overlap")
    for path in local_objects:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"invalid local runtime object: {path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    member_directory = output.parent / "runtime-members"
    if member_directory.is_symlink():
        raise ValueError(f"refusing symlinked member directory: {member_directory}")
    member_directory.mkdir(exist_ok=True)

    extracted: list[Path] = []
    for member in members:
        data = subprocess.run(
            [str(ar), "p", str(source_archive), member],
            check=True,
            capture_output=True,
        ).stdout
        if not data:
            raise ValueError(f"empty or missing archive member: {member}")
        destination = member_directory / member
        if destination.is_symlink():
            raise ValueError(f"refusing symlinked member output: {destination}")
        destination.write_bytes(data)
        extracted.append(destination)

    temporary = output.with_name(f".{output.name}.tmp")
    if temporary.is_symlink():
        raise ValueError(f"refusing symlinked temporary archive: {temporary}")
    temporary.unlink(missing_ok=True)
    try:
        subprocess.run(
            [str(ar), "rcs", str(temporary)]
            + [str(path) for path in local_objects]
            + [str(path) for path in extracted],
            check=True,
        )
        observed = subprocess.run(
            [str(ar), "t", str(temporary)],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.splitlines()
        if observed != expected:
            raise ValueError(
                f"restricted archive members differ: expected {expected}, got {observed}"
            )
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return expected


def parse_args(argv: list[str]) -> argparse.Namespace:
    runtime_root = Path(__file__).resolve().parent
    repository = runtime_root.parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ar",
        type=Path,
        default=repository / "toolchains/agondev/bin/ez80-none-elf-ar",
    )
    parser.add_argument(
        "--source-archive",
        type=Path,
        default=repository / "toolchains/agondev/lib/libagon.a",
    )
    parser.add_argument(
        "--local-object",
        action="append",
        type=Path,
        default=[
            runtime_root / "build/firmware_printf.o",
            runtime_root / "build/i48_required.o",
        ],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=runtime_root / "build/libmos_runtime.a",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=runtime_root / "runtime_policy.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    try:
        members = build(
            ar=args.ar.resolve(),
            source_archive=args.source_archive.resolve(),
            local_objects=[path.resolve() for path in args.local_object],
            output=args.output.resolve(),
            policy=policy,
        )
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"wrote {args.output} with {len(members)} explicitly selected members")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
