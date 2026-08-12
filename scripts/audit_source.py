#!/usr/bin/env python3
"""Produce a deterministic audit of the pinned MOS/toolchain/emulator inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MOS = PROJECT_ROOT / "upstream/agon-mos"
DEFAULT_AGONDEV = PROJECT_ROOT / "../../agondev"
DEFAULT_FAB = PROJECT_ROOT / "../../fab-agon-emulator"
DEFAULT_DOCS = PROJECT_ROOT / "../../agon-docs"


def run(*args: str | Path) -> str:
    result = subprocess.run(
        [str(arg) for arg in args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def git_identity(repository: Path) -> dict[str, Any]:
    return {
        "commit": run("git", "-C", repository, "rev-parse", "HEAD"),
        "describe": run(
            "git", "-C", repository, "describe", "--always", "--dirty", "--tags"
        ),
        "dirty": bool(run("git", "-C", repository, "status", "--porcelain")),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def line_count(paths: list[Path]) -> int:
    # Match the conventional `wc -l` metric used for the source audit.
    return sum(path.read_bytes().count(b"\n") for path in paths)


def assembly_construct_counts(paths: list[Path]) -> dict[str, int]:
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in paths)
    flags = re.IGNORECASE | re.MULTILINE
    patterns = {
        "percent_hex_literals": r"%[0-9A-F]+",
        "forward_backward_local_refs": r"\$[FB]\b",
        "dollar_dollar_local_definitions": r"\$\$:",
        "binary_suffix_literals": r"\b[01]{4,}b\b",
        "dl_or_dw24_directives": r"^\s*(?:[A-Za-z_.$?][\w.$?]*:\s*)?(?:DL|DW24)\b",
        "scope_directives": r"^\s*SCOPE\b",
        "zds_macro_definitions": r"^\s*[A-Za-z_.$?][\w.$?]*:?\s+MACRO(?:\s|$)",
        "define_space_directives": r"^\s*DEFINE\s+\S+\s*,?\s*SPACE\b",
        "segment_directives": r"^\s*SEGMENT\b",
        "wide_register_copy_pseudo_ops": (
            r"\bLD\s+(?:BC|DE|HL|IX|IY)\s*,\s*(?:BC|DE|HL|IX|IY)\b"
        ),
    }
    return {name: len(re.findall(pattern, text, flags)) for name, pattern in patterns.items()}


def parse_zds_space_allocation(map_text: str) -> dict[str, dict[str, int | str]]:
    spaces: dict[str, dict[str, int | str]] = {}
    pattern = re.compile(
        r"^(RAM|ROM)\s+[CD]:([0-9A-F]+)\s+[CD]:([0-9A-F]+)\s+"
        r"([0-9A-F]+)H\s+([0-9A-F]+)H\s+([0-9A-F]+)H\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in pattern.finditer(map_text):
        name, base, top, capacity, used, unused = match.groups()
        spaces[name.lower()] = {
            "base": f"0x{int(base, 16):06x}",
            "top": f"0x{int(top, 16):06x}",
            "capacity_bytes": int(capacity, 16),
            "used_bytes": int(used, 16),
            "unused_bytes": int(unused, 16),
        }
    if set(spaces) != {"ram", "rom"}:
        raise ValueError("could not find RAM and ROM allocation rows in ZDS map")
    return spaces


def file_identity(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def build_audit(mos: Path, agondev: Path, fab: Path, docs: Path) -> dict[str, Any]:
    c_sources = sorted(mos.rglob("*.c"))
    assembly_sources = sorted([*mos.rglob("*.asm"), *mos.rglob("*.inc")])
    firmware = fab / "firmware"
    platform_map = firmware / "mos_platform.map"
    toolbin = agondev / "release/bin"
    return {
        "schema": 1,
        "repositories": {
            "agon_mos": git_identity(mos),
            "agondev": git_identity(agondev),
            "fab_agon_emulator": git_identity(fab),
            "agon_docs": git_identity(docs),
        },
        "toolchain": {
            "agondev_config": run(toolbin / "agondev-config", "--version"),
            "clang": run(toolbin / "ez80-none-elf-clang", "--version").splitlines()[0],
            "binutils_ld": run(toolbin / "ez80-none-elf-ld", "--version").splitlines()[0],
        },
        "source": {
            "c_files": len(c_sources),
            "c_lines": line_count(c_sources),
            "assembly_and_include_files": len(assembly_sources),
            "assembly_and_include_lines": line_count(assembly_sources),
            "zds_constructs": assembly_construct_counts(assembly_sources),
        },
        "stock_platform": {
            "space_allocation": parse_zds_space_allocation(
                platform_map.read_text(encoding="utf-8", errors="replace")
            ),
            "fab_executable": file_identity(fab / "fab-agon-emulator"),
            "mos": file_identity(firmware / "mos_platform.bin"),
            "map": file_identity(platform_map),
            "vdp": file_identity(firmware / "vdp_platform.so"),
        },
        "measured_probes": {
            "agondev_c_translation_units": 16,
            "agondev_c_loadable_bytes_before_runtime_and_assembly": 88054,
            "zds_c_loadable_bytes": 95238,
            "firmware_probe_sha256": (
                "28528ac57eb024dfa2afad063db102cb11d115c87c2d3dfaf65bdb27a47647a9"
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mos", type=Path, default=DEFAULT_MOS)
    parser.add_argument("--agondev", type=Path, default=DEFAULT_AGONDEV)
    parser.add_argument("--fab", type=Path, default=DEFAULT_FAB)
    parser.add_argument("--docs", type=Path, default=DEFAULT_DOCS)
    parser.add_argument(
        "--check", type=Path, help="fail if the generated audit differs from this file"
    )
    parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = build_audit(
        args.mos.expanduser().resolve(),
        args.agondev.expanduser().resolve(),
        args.fab.expanduser().resolve(),
        args.docs.expanduser().resolve(),
    )
    rendered = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    if args.check:
        expected = json.loads(args.check.read_text(encoding="utf-8"))
        if audit != expected:
            print(f"Audit differs from {args.check}", file=sys.stderr)
            return 1
        print(f"Audit matches {args.check}")
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    elif not args.check:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
