#!/usr/bin/env python3
"""Audit the exact firmware runtime closure selected from libagon.a."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    owner: str


def run_nm(nm: Path, target: Path) -> list[Symbol]:
    command = [str(nm), "-P", "-A", "-g", str(target)]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    symbols: list[Symbol] = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) < 3 or not fields[0].endswith(":"):
            raise ValueError(f"unrecognized nm output: {line!r}")
        owner = fields[0][:-1]
        symbols.append(Symbol(name=fields[1], kind=fields[2], owner=owner))
    return symbols


def archive_relocations(readelf: Path, archive: Path) -> dict[str, set[str]]:
    completed = subprocess.run(
        [str(readelf), "-r", str(archive)],
        check=True,
        text=True,
        capture_output=True,
    )
    references: dict[str, set[str]] = defaultdict(set)
    member: str | None = None
    for line in completed.stdout.splitlines():
        file_match = re.match(r"File: .*\(([^()]+)\)$", line)
        if file_match:
            member = file_match.group(1)
            continue
        fields = line.split()
        if member is not None and len(fields) >= 5 and re.fullmatch(
            r"[0-9A-Fa-f]+", fields[0]
        ):
            references[member].add(fields[4])
    return references


def object_relocations(readelf: Path, target: Path) -> set[str]:
    completed = subprocess.run(
        [str(readelf), "-r", str(target)],
        check=True,
        text=True,
        capture_output=True,
    )
    references: set[str] = set()
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 5 and re.fullmatch(r"[0-9A-Fa-f]+", fields[0]):
            references.add(fields[4])
    return references


def archive_member(owner: str) -> str:
    match = re.search(r"\[([^][]+)\]$", owner)
    if not match:
        raise ValueError(f"archive symbol lacks member name: {owner!r}")
    return match.group(1)


def assembly_exports(source_root: Path) -> set[str]:
    exports: set[str] = set()
    for source in sorted(source_root.rglob("*.asm")):
        for raw_line in source.read_text(encoding="utf-8", errors="strict").splitlines():
            code = raw_line.split(";", 1)[0]
            match = re.search(r"\bXDEF\b(.*)$", code, flags=re.IGNORECASE)
            if not match:
                continue
            for name in re.findall(r"[A-Za-z_.][A-Za-z0-9_.$]*", match.group(1)):
                exports.add(name)
    return exports


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def section_sizes(size: Path, target: Path) -> dict[str, int]:
    completed = subprocess.run(
        [str(size), "-A", str(target)],
        check=True,
        text=True,
        capture_output=True,
    )
    totals: dict[str, int] = defaultdict(int)
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0].startswith(".") and fields[1].isdigit():
            totals[fields[0]] += int(fields[1])
    return dict(sorted(totals.items()))


def configured_c_objects(objects_root: Path, names: Iterable[str]) -> list[Path]:
    result: list[Path] = []
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".o":
            raise ValueError(f"unsafe configured C object path: {name!r}")
        path = objects_root / relative
        if path in result:
            raise ValueError(f"duplicate configured C object path: {name}")
        result.append(path)
    return result


def audit(
    nm: Path,
    readelf: Path,
    ar: Path,
    size: Path,
    objects_root: Path,
    archive: Path,
    nanoprintf: Path,
    assembly_root: Path,
    local_objects: Iterable[Path],
    link_probe: Path,
    runtime_archive: Path,
    policy: dict[str, object],
) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    try:
        object_paths = configured_c_objects(objects_root, policy["c_objects"])
    except ValueError as error:
        return {}, [str(error)]
    missing_objects = [str(path) for path in object_paths if not path.is_file()]
    if missing_objects:
        return {}, [f"configured C objects are missing: {missing_objects}"]

    object_symbols = [symbol for path in object_paths for symbol in run_nm(nm, path)]
    object_definitions = {s.name for s in object_symbols if s.kind.upper() != "U"}
    object_undefined = {s.name for s in object_symbols if s.kind.upper() == "U"}
    demands = object_undefined - object_definitions

    configured_local = set(policy["local_symbols"])
    local_definitions: set[str] = set()
    local_undefined: set[str] = set()
    for path in local_objects:
        if not path.is_file():
            errors.append(f"local runtime object is missing: {path}")
            continue
        for symbol in run_nm(nm, path):
            if symbol.kind.upper() == "U":
                local_undefined.add(symbol.name)
            else:
                local_definitions.add(symbol.name)
    missing_local = configured_local - local_definitions
    unexpected_local = local_definitions - configured_local
    if missing_local:
        errors.append(f"local runtime exports missing: {sorted(missing_local)}")
    if unexpected_local:
        errors.append(f"unallowlisted local runtime exports: {sorted(unexpected_local)}")
    demands |= local_undefined

    actual_archive_hash = sha256(archive)
    if actual_archive_hash != policy["archive_sha256"]:
        errors.append(
            "libagon archive hash mismatch: "
            f"expected {policy['archive_sha256']}, got {actual_archive_hash}"
        )
    actual_nanoprintf_hash = sha256(nanoprintf)
    if actual_nanoprintf_hash != policy["nanoprintf_sha256"]:
        errors.append(
            "nanoprintf input hash mismatch: "
            f"expected {policy['nanoprintf_sha256']}, got {actual_nanoprintf_hash}"
        )

    archive_symbols = run_nm(nm, archive)
    relocation_references = archive_relocations(readelf, archive)
    member_definitions: dict[str, set[str]] = defaultdict(set)
    member_undefined: dict[str, set[str]] = defaultdict(set)
    symbol_providers: dict[str, list[str]] = defaultdict(list)
    for symbol in archive_symbols:
        member = archive_member(symbol.owner)
        if symbol.kind.upper() == "U":
            member_undefined[member].add(symbol.name)
        else:
            member_definitions[member].add(symbol.name)
            if member not in symbol_providers[symbol.name]:
                symbol_providers[symbol.name].append(member)

    assembly = assembly_exports(assembly_root)
    linker = set(policy["linker_symbols"])
    base_definitions = object_definitions | local_definitions | assembly | linker

    selected: list[str] = []
    selected_set: set[str] = set()
    selected_definitions: set[str] = set()
    pending = deque(sorted(demands - base_definitions))
    unresolved: set[str] = set()
    while pending:
        symbol = pending.popleft()
        if symbol in base_definitions or symbol in selected_definitions:
            continue
        providers = symbol_providers.get(symbol, [])
        if not providers:
            unresolved.add(symbol)
            continue
        member = providers[0]
        if member in selected_set:
            unresolved.add(symbol)
            continue
        selected.append(member)
        selected_set.add(member)
        selected_definitions |= member_definitions[member]
        linked_dependencies = member_undefined[member] & relocation_references[member]
        for dependency in sorted(linked_dependencies):
            if dependency not in base_definitions and dependency not in selected_definitions:
                pending.append(dependency)

    allowed_categories = policy["allowed_archive_members"]
    allowed: set[str] = set()
    for category, members in allowed_categories.items():
        overlap = allowed & set(members)
        if overlap:
            errors.append(
                f"archive members occur in multiple allow-list categories: {sorted(overlap)}"
            )
        allowed |= set(members)
    forbidden = set(policy["forbidden_archive_members"])
    unallowlisted = selected_set - allowed
    stale_allowlist = allowed - selected_set
    selected_forbidden = selected_set & forbidden
    if unallowlisted:
        errors.append(f"archive members are not allow-listed: {sorted(unallowlisted)}")
    if stale_allowlist:
        errors.append(f"allow-listed archive members were not selected: {sorted(stale_allowlist)}")
    if selected_forbidden:
        errors.append(f"forbidden archive members selected: {sorted(selected_forbidden)}")
    if unresolved:
        errors.append(f"unresolved symbols after runtime closure: {sorted(unresolved)}")

    provider_for: dict[str, str] = {}
    for symbol in sorted(demands):
        if symbol in object_definitions:
            provider_for[symbol] = "c-object"
        elif symbol in local_definitions:
            provider_for[symbol] = "local"
        elif symbol in assembly:
            provider_for[symbol] = "assembly"
        elif symbol in linker:
            provider_for[symbol] = "linker"
        elif symbol in selected_definitions:
            provider_for[symbol] = "archive"
        else:
            provider_for[symbol] = "unresolved"

    for symbol, required in policy["required_providers"].items():
        actual = provider_for.get(symbol, "not-demanded")
        if actual != required:
            errors.append(f"{symbol} must be provided by {required}, got {actual}")

    shadowed_archive = {
        symbol: symbol_providers[symbol]
        for symbol, provider in provider_for.items()
        if provider != "archive" and symbol_providers.get(symbol)
    }
    link_probe_symbols = run_nm(nm, link_probe)
    link_probe_undefined = {
        symbol.name for symbol in link_probe_symbols if symbol.kind.upper() == "U"
    }
    link_probe_relocations = object_relocations(readelf, link_probe)
    linked_undefined = link_probe_undefined & link_probe_relocations
    metadata_only = link_probe_undefined - link_probe_relocations
    unexpected_linked = linked_undefined - assembly - linker
    expected_metadata = set(policy["metadata_only_undefined"])
    if unexpected_linked:
        errors.append(
            "link probe retains unexpected relocated undefined symbols: "
            f"{sorted(unexpected_linked)}"
        )
    if metadata_only != expected_metadata:
        errors.append(
            "link probe metadata-only undefined symbols differ: "
            f"expected {sorted(expected_metadata)}, got {sorted(metadata_only)}"
        )
    expected_restricted_members = [path.name for path in local_objects] + [
        member for members in allowed_categories.values() for member in members
    ]
    observed_restricted_members = subprocess.run(
        [str(ar), "t", str(runtime_archive)],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    if observed_restricted_members != expected_restricted_members:
        errors.append(
            "restricted archive member list differs from policy: "
            f"expected {expected_restricted_members}, got {observed_restricted_members}"
        )
    runtime_sections = section_sizes(size, runtime_archive)
    link_probe_sections = section_sizes(size, link_probe)
    report: dict[str, object] = {
        "archive": str(archive),
        "archive_sha256": actual_archive_hash,
        "nanoprintf": str(nanoprintf),
        "nanoprintf_sha256": actual_nanoprintf_hash,
        "c_object_count": len(object_paths),
        "c_external_symbol_count": len(object_undefined - object_definitions),
        "local_runtime_undefined": sorted(local_undefined),
        "link_probe_relocated_undefined": sorted(linked_undefined),
        "link_probe_metadata_only_undefined": sorted(metadata_only),
        "link_probe_sections": link_probe_sections,
        "provider_counts": {
            provider: sum(1 for value in provider_for.values() if value == provider)
            for provider in sorted(set(provider_for.values()))
        },
        "selected_archive_members": selected,
        "selected_archive_member_count": len(selected),
        "selected_archive_categories": {
            category: sorted(selected_set & set(members))
            for category, members in allowed_categories.items()
        },
        "selected_archive_symbols": {
            member: sorted(member_definitions[member]) for member in selected
        },
        "restricted_runtime_archive": str(runtime_archive),
        "restricted_runtime_members": observed_restricted_members,
        "restricted_runtime_sections": runtime_sections,
        "restricted_runtime_loadable_bytes": sum(
            runtime_sections.get(section, 0) for section in (".text", ".rodata", ".data")
        ),
        "shadowed_archive_providers": shadowed_archive,
        "unresolved_symbols": sorted(unresolved),
    }
    return report, errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    runtime_root = Path(__file__).resolve().parent
    repository = runtime_root.parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--nm",
        type=Path,
        default=repository / "toolchains/agondev/bin/ez80-none-elf-nm",
    )
    parser.add_argument(
        "--readelf",
        type=Path,
        default=repository / "toolchains/agondev/bin/ez80-none-elf-readelf",
    )
    parser.add_argument(
        "--ar",
        type=Path,
        default=repository / "toolchains/agondev/bin/ez80-none-elf-ar",
    )
    parser.add_argument(
        "--size",
        type=Path,
        default=repository / "toolchains/agondev/bin/ez80-none-elf-size",
    )
    parser.add_argument(
        "--objects",
        type=Path,
        default=repository / "projects/mos-port/obj",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=repository / "toolchains/agondev/lib/libagon.a",
    )
    parser.add_argument(
        "--nanoprintf",
        type=Path,
        default=runtime_root / "vendor/nanoprintf/nanoprintf.h",
    )
    parser.add_argument(
        "--assembly",
        type=Path,
        default=repository / "projects/mos-port/worktree",
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
        "--link-probe",
        type=Path,
        default=runtime_root / "build/c-runtime-linked.o",
    )
    parser.add_argument(
        "--runtime-archive",
        type=Path,
        default=runtime_root / "build/libmos_runtime.a",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=runtime_root / "runtime_policy.json",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    report, errors = audit(
        nm=args.nm.resolve(),
        readelf=args.readelf.resolve(),
        ar=args.ar.resolve(),
        size=args.size.resolve(),
        objects_root=args.objects.resolve(),
        archive=args.archive.resolve(),
        nanoprintf=args.nanoprintf.resolve(),
        assembly_root=args.assembly.resolve(),
        local_objects=[path.resolve() for path in args.local_object],
        link_probe=args.link_probe.resolve(),
        runtime_archive=args.runtime_archive.resolve(),
        policy=policy,
    )
    if args.json:
        print(json.dumps({"errors": errors, **report}, indent=2, sort_keys=True))
    else:
        print(f"C external symbols: {report.get('c_external_symbol_count', 0)}")
        print(f"providers: {report.get('provider_counts', {})}")
        print(
            "selected libagon members: "
            + ", ".join(report.get("selected_archive_members", []))
        )
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
