#!/usr/bin/env python3
"""Collect deterministic, inspectable artifacts from an AgonDev MOS build."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parents[1]
DEFAULT_MOS_PORT = ROOT / "projects" / "mos-port"
DEFAULT_TOOLCHAIN = ROOT / "toolchains" / "agondev"
DEFAULT_SOURCE_REPO = ROOT / "upstream" / "agon-mos"
DEFAULT_OUTPUT = PROJECT / "artifacts" / "candidate"


class CollectionError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular(path: Path, description: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise CollectionError(f"{description} is not a regular file: {path}")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise CollectionError(f"temporary output already exists: {temporary}")
    temporary.write_bytes(data)
    temporary.replace(path)


def sanitized_command(
    command: list[str], *, cwd: Path, replacements: dict[bytes, bytes]
) -> bytes:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise CollectionError(f"command failed ({result.returncode}): {command}\n{stderr}")
    data = result.stdout
    for old, new in sorted(replacements.items(), key=lambda item: -len(item[0])):
        data = data.replace(old, new)
    return data


def copy_regular(source: Path, destination: Path) -> None:
    require_regular(source, "candidate artifact")
    write_bytes(destination, source.read_bytes())


def preparation_changes(
    source_repo: Path, worktree: Path, provenance: dict[str, Any]
) -> list[dict[str, Any]]:
    source = provenance.get("source")
    files = provenance.get("files")
    if not isinstance(source, dict) or not isinstance(files, list):
        raise CollectionError("prepared-source provenance has an invalid schema")
    expected_head = source.get("head")
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=source_repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0 or result.stdout.strip() != expected_head:
        raise CollectionError("configured source HEAD does not match prepared-source provenance")
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=no",
            "--ignore-submodules=none",
        ],
        cwd=source_repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if status.returncode != 0:
        raise CollectionError("cannot read configured source worktree status")
    if bool(status.stdout) is not source.get("tracked_dirty"):
        raise CollectionError(
            "configured source tracked-dirty state changed since worktree preparation"
        )
    changes = []
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise CollectionError("prepared-source provenance contains an invalid file")
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise CollectionError("prepared-source provenance contains an unsafe path")
        original = source_repo / relative
        prepared = worktree / relative
        require_regular(original, "configured source file")
        require_regular(prepared, "prepared source file")
        original_bytes = original.read_bytes()
        prepared_bytes = prepared.read_bytes()
        if original_bytes == prepared_bytes:
            continue
        item: dict[str, Any] = {
            "path": relative.as_posix(),
            "source_sha256": hashlib.sha256(original_bytes).hexdigest(),
            "prepared_sha256": hashlib.sha256(prepared_bytes).hexdigest(),
        }
        try:
            original_text = original_bytes.decode("utf-8")
            prepared_text = prepared_bytes.decode("utf-8")
        except UnicodeDecodeError:
            item["diff"] = None
        else:
            item["diff"] = "".join(
                difflib.unified_diff(
                    original_text.splitlines(keepends=True),
                    prepared_text.splitlines(keepends=True),
                    fromfile=f"source/{relative.as_posix()}",
                    tofile=f"prepared/{relative.as_posix()}",
                    n=3,
                )
            )
        changes.append(item)
    return changes


def collect(args: argparse.Namespace) -> dict[str, Any]:
    mos_port = args.mos_port.resolve()
    toolchain = args.toolchain.resolve()
    source_repo = args.source_repo.resolve()
    output = args.output.resolve()
    if output.is_symlink():
        raise CollectionError(f"output directory may not be a symlink: {output}")
    output.mkdir(parents=True, exist_ok=True)
    if not output.is_dir() or output.is_symlink():
        raise CollectionError(f"unsafe output directory: {output}")
    expected_outputs: set[str] = set()

    toolbin = toolchain / "bin"
    tools = {
        "nm": toolbin / "ez80-none-elf-nm",
        "objdump": toolbin / "ez80-none-elf-objdump",
        "readelf": toolbin / "ez80-none-elf-readelf",
    }
    for name, path in tools.items():
        require_regular(path, f"{name} tool")

    inputs = {
        "MOS.bin": mos_port / "bin" / "MOS.bin",
        "MOS.elf": mos_port / "bin" / "MOS.elf",
        "MOS.map": mos_port / "bin" / "MOS.map",
        "generated-manifest.json": mos_port / "generated" / "manifest.json",
        "source-provenance.json": mos_port / "worktree" / ".mos-agondev-worktree.json",
    }
    for name, path in inputs.items():
        require_regular(path, name)
        copy_regular(path, output / name)
        expected_outputs.add(name)

    provenance = json.loads(inputs["source-provenance.json"].read_text(encoding="utf-8"))
    changes = preparation_changes(source_repo, mos_port / "worktree", provenance)
    write_bytes(
        output / "preparation-diff.json",
        (json.dumps({"schema": 1, "changes": changes}, indent=2, sort_keys=True) + "\n").encode(),
    )
    expected_outputs.add("preparation-diff.json")

    replacements = {
        str(ROOT.resolve()).encode(): b"<repo>",
        str(toolchain).encode(): b"<toolchain>",
    }
    commands: dict[str, tuple[list[str], str]] = {
        "linked.nm": (
            [str(tools["nm"]), "-n", "-S", "--defined-only", str(inputs["MOS.elf"])],
            "nm",
        ),
        "linked.disassembly.txt": (
            [str(tools["objdump"]), "-d", "-M", "adl", str(inputs["MOS.elf"])],
            "objdump",
        ),
        "linked.sections.txt": (
            [str(tools["readelf"]), "-SW", str(inputs["MOS.elf"])],
            "readelf",
        ),
        "linked.relocations.txt": (
            [str(tools["readelf"]), "-rW", str(inputs["MOS.elf"])],
            "readelf",
        ),
    }
    for output_name, (command, _) in commands.items():
        write_bytes(
            output / output_name,
            sanitized_command(command, cwd=mos_port, replacements=replacements),
        )
        expected_outputs.add(output_name)

    object_root = mos_port / "obj"
    if not object_root.is_dir() or object_root.is_symlink():
        raise CollectionError(f"candidate object directory is unavailable: {object_root}")
    objects = sorted(
        path for path in object_root.rglob("*.o") if path.is_file() and not path.is_symlink()
    )
    for object_path in objects:
        relative = object_path.relative_to(object_root)
        stem = relative.as_posix()
        disassembly = sanitized_command(
            [str(tools["objdump"]), "-dr", "-M", "adl", str(object_path)],
            cwd=mos_port,
            replacements=replacements,
        )
        symbols = sanitized_command(
            [str(tools["nm"]), "-n", "-S", "--defined-only", str(object_path)],
            cwd=mos_port,
            replacements=replacements,
        )
        write_bytes(output / "objects" / f"{stem}.disassembly.txt", disassembly)
        write_bytes(output / "objects" / f"{stem}.nm", symbols)
        expected_outputs.add(f"objects/{stem}.disassembly.txt")
        expected_outputs.add(f"objects/{stem}.nm")

    runtime_archive = mos_port / "runtime" / "build" / "libmos_runtime.a"
    require_regular(runtime_archive, "restricted runtime archive")
    write_bytes(
        output / "runtime-archive.disassembly.txt",
        sanitized_command(
            [str(tools["objdump"]), "-dr", "-M", "adl", str(runtime_archive)],
            cwd=mos_port,
            replacements=replacements,
        ),
    )
    write_bytes(
        output / "runtime-archive.nm",
        sanitized_command(
            [str(tools["nm"]), "-n", "-S", "--defined-only", str(runtime_archive)],
            cwd=mos_port,
            replacements=replacements,
        ),
    )
    expected_outputs.update(
        {"runtime-archive.disassembly.txt", "runtime-archive.nm"}
    )

    for source_root, destination_name, pattern in (
        (mos_port / "generated", "generated-assembly", "*.asm"),
        (mos_port / "inspect" / "c", "compiler-assembly", "*.s"),
    ):
        if not source_root.is_dir() or source_root.is_symlink():
            raise CollectionError(f"inspection source directory is unavailable: {source_root}")
        for source in sorted(source_root.rglob(pattern)):
            if source.is_symlink() or not source.is_file():
                raise CollectionError(f"unsafe inspection source: {source}")
            relative = source.relative_to(source_root)
            data = source.read_bytes()
            for old, new in sorted(replacements.items(), key=lambda item: -len(item[0])):
                data = data.replace(old, new)
            write_bytes(output / destination_name / relative, data)
            expected_outputs.add(f"{destination_name}/{relative.as_posix()}")

    tool_versions = {}
    for name, path in tools.items():
        first_line = sanitized_command(
            [str(path), "--version"], cwd=mos_port, replacements=replacements
        ).decode("utf-8", errors="strict").splitlines()[0]
        tool_versions[name] = first_line

    actual_outputs = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != "manifest.json"
    }
    if actual_outputs != expected_outputs:
        raise CollectionError(
            "candidate output contains stale or missing artifacts; remove the ignored "
            f"candidate directory and rerun (missing={sorted(expected_outputs - actual_outputs)}, "
            f"extra={sorted(actual_outputs - expected_outputs)})"
        )
    files = []
    for path in sorted(output.rglob("*")):
        if path.name == "manifest.json":
            continue
        if path.is_symlink():
            raise CollectionError(f"symlink appeared in candidate artifacts: {path}")
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(output).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = {
        "schema": 1,
        "tools": tool_versions,
        "object_count": len(objects),
        "files": files,
    }
    write_bytes(
        output / "manifest.json",
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    )
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mos-port", type=Path, default=DEFAULT_MOS_PORT)
    parser.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    parser.add_argument("--source-repo", type=Path, default=DEFAULT_SOURCE_REPO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        manifest = collect(parse_args(argv))
        print(
            f"candidate inspection captured: {manifest['object_count']} objects, "
            f"{len(manifest['files'])} files"
        )
        return 0
    except (CollectionError, OSError, UnicodeDecodeError) as exc:
        print(f"collection error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
