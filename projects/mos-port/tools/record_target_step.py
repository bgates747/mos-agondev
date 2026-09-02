#!/usr/bin/env python3
"""Execute one target build step and record fail-closed provenance.

The recorder is deliberately generic: product profiles select source units,
while this tool records the compiler, assembler, and linker processes that
actually run.  It is not a sandbox and must only execute reviewed build
commands from trusted Makefiles.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Iterable, Sequence
import uuid


SCHEMA_VERSION = 1
ROOT_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
NORMALIZATION_BOUNDARY = r"(?=$|/|[\s\"'`,;:\]\)])"
SESSION_MARKER = ".mos-agondev-provenance-session.json"
CHILD_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
}
CLEARED_ENVIRONMENT = (
    "CPATH",
    "C_INCLUDE_PATH",
    "CPLUS_INCLUDE_PATH",
    "OBJC_INCLUDE_PATH",
    "LIBRARY_PATH",
    "COMPILER_PATH",
    "GCC_EXEC_PREFIX",
    "DEPENDENCIES_OUTPUT",
    "SUNPRO_DEPENDENCIES",
    "SOURCE_DATE_EPOCH",
)


class ProvenanceError(ValueError):
    """A build step could not produce trustworthy provenance."""


@dataclass(frozen=True)
class Root:
    name: str
    lexical: str
    resolved: str


@dataclass(frozen=True)
class FileState:
    lexical: Path
    resolved: Path
    normalized: str
    sha256: str
    size: int
    leaf_symlink: bool = False

    def record(self) -> dict[str, object]:
        return {
            "path": self.normalized,
            "sha256": self.sha256,
            "size": self.size,
        }


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def lexical_absolute(path: Path, cwd: Path) -> Path:
    value = path if path.is_absolute() else cwd / path
    return Path(os.path.abspath(os.fspath(value)))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _owning_root(path: Path, roots: Sequence[Root], description: str) -> Root:
    matches = [root for root in roots if _is_within(path, Path(root.lexical))]
    if not matches:
        raise ProvenanceError(
            f"{description} is outside every declared lexical root: {path}"
        )
    return max(matches, key=lambda item: len(item.lexical))


def _reject_symlink_components_below_root(
    path: Path, root: Root, description: str
) -> None:
    relative = path.relative_to(Path(root.lexical))
    cursor = Path(root.lexical)
    for component in relative.parts:
        cursor /= component
        if os.path.lexists(cursor) and cursor.is_symlink():
            raise ProvenanceError(
                f"{description} has a symbolic-link component below "
                f"root {root.name}: {cursor}"
            )


def _require_no_root_escape(
    path: Path,
    resolved: Path,
    roots: Sequence[Root],
    description: str,
    *,
    allow_leaf_symlink: bool = False,
) -> Root:
    root = _owning_root(path, roots, description)
    leaf_symlink = allow_leaf_symlink and path.is_symlink()
    component_path = path.parent if leaf_symlink else path
    _reject_symlink_components_below_root(component_path, root, description)
    if not leaf_symlink and not _is_within(resolved, Path(root.resolved)):
        raise ProvenanceError(
            f"{description} resolves outside root {root.name}: {path} -> {resolved}"
        )
    return root


def _nearest_existing(path: Path) -> Path:
    cursor = path
    while not os.path.lexists(cursor):
        parent = cursor.parent
        if parent == cursor:
            raise ProvenanceError(f"path has no existing ancestor: {path}")
        cursor = parent
    return cursor


def parse_roots(values: Iterable[str], cwd: Path) -> list[Root]:
    result: list[Root] = []
    names: set[str] = set()
    lexical_roots: set[str] = set()
    resolved_roots: set[str] = set()
    for raw in values:
        if "=" not in raw:
            raise ProvenanceError(f"root must use NAME=PATH syntax: {raw!r}")
        name, raw_path = raw.split("=", 1)
        if ROOT_NAME.fullmatch(name) is None or name in names:
            raise ProvenanceError(f"invalid or duplicate root name: {name!r}")
        if not raw_path:
            raise ProvenanceError(f"root path is empty: {name}")
        lexical_path = lexical_absolute(Path(raw_path), cwd)
        try:
            resolved_path = lexical_path.resolve(strict=True)
        except FileNotFoundError as error:
            raise ProvenanceError(f"root does not exist: {name}={lexical_path}") from error
        if not resolved_path.is_dir():
            raise ProvenanceError(f"root is not a directory: {name}={lexical_path}")
        lexical_text = os.fspath(lexical_path)
        resolved_text = os.fspath(resolved_path)
        if lexical_text in lexical_roots or resolved_text in resolved_roots:
            raise ProvenanceError(f"aliased or duplicate root path: {name}={lexical_path}")
        names.add(name)
        lexical_roots.add(lexical_text)
        resolved_roots.add(resolved_text)
        result.append(Root(name, lexical_text, resolved_text))
    return sorted(
        result,
        key=lambda item: max(len(item.lexical), len(item.resolved)),
        reverse=True,
    )


def normalize(value: str, roots: Sequence[Root]) -> str:
    candidates: list[tuple[str, str]] = []
    for root in roots:
        replacement = "${" + root.name + "}"
        candidates.extend(
            (candidate, replacement)
            for candidate in sorted({root.lexical, root.resolved})
        )
    result = value
    for candidate, replacement in sorted(
        candidates, key=lambda item: len(item[0]), reverse=True
    ):
        result = re.sub(
            re.escape(candidate) + NORMALIZATION_BOUNDARY, replacement, result
        )
    return result


def regular_file_state(
    path: Path, cwd: Path, roots: Sequence[Root], description: str
) -> FileState:
    lexical = lexical_absolute(path, cwd)
    if lexical.is_symlink():
        raise ProvenanceError(f"{description} must not be a symbolic link: {lexical}")
    try:
        resolved = lexical.resolve(strict=True)
    except FileNotFoundError as error:
        raise ProvenanceError(f"{description} does not exist: {lexical}") from error
    if not resolved.is_file():
        raise ProvenanceError(f"{description} is not a regular file: {lexical}")
    _require_no_root_escape(lexical, resolved, roots, description)
    return FileState(
        lexical=lexical,
        resolved=resolved,
        normalized=normalize(os.fspath(lexical), roots),
        sha256=sha256_file(resolved),
        size=resolved.stat().st_size,
        leaf_symlink=False,
    )


def absent_file(
    path: Path, cwd: Path, roots: Sequence[Root], description: str
) -> Path:
    lexical = lexical_absolute(path, cwd)
    if os.path.lexists(lexical):
        raise ProvenanceError(
            f"refusing stale {description}; remove it with the owning clean target: "
            f"{lexical}"
        )
    root = _owning_root(lexical, roots, description)
    existing = _nearest_existing(lexical)
    _reject_symlink_components_below_root(existing, root, description)
    resolved = existing.resolve(strict=True)
    if not _is_within(resolved, Path(root.resolved)):
        raise ProvenanceError(
            f"{description} would escape root {root.name}: {lexical}"
        )
    return lexical


def resolve_executable(value: str, cwd: Path) -> Path:
    if "/" in value:
        candidate = lexical_absolute(Path(value), cwd)
    else:
        found = shutil.which(value)
        if found is None:
            raise ProvenanceError(f"executable is not on PATH: {value}")
        candidate = Path(found)
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise ProvenanceError(f"executable does not exist: {candidate}") from error
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ProvenanceError(f"executable is not an executable file: {candidate}")
    return candidate


def executable_record(
    executable: Path, cwd: Path, roots: Sequence[Root]
) -> tuple[dict[str, object], FileState]:
    lexical = lexical_absolute(executable, cwd)
    try:
        resolved = lexical.resolve(strict=True)
    except FileNotFoundError as error:
        raise ProvenanceError(f"declared executable does not exist: {lexical}") from error
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ProvenanceError(f"declared executable is not executable: {lexical}")
    _require_no_root_escape(
        lexical,
        resolved,
        roots,
        "declared executable",
        allow_leaf_symlink=True,
    )
    state = FileState(
        lexical=lexical,
        resolved=resolved,
        normalized=normalize(os.fspath(lexical), roots),
        sha256=sha256_file(resolved),
        size=resolved.stat().st_size,
        leaf_symlink=lexical.is_symlink(),
    )
    completed = subprocess.run(
        [os.fspath(executable), "--version"],
        cwd=cwd,
        env=CHILD_ENVIRONMENT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise ProvenanceError(
            f"version command failed for {executable}: exit {completed.returncode}"
        )
    version_bytes = completed.stdout + completed.stderr
    version_output = normalize(
        version_bytes.decode("utf-8", errors="replace").strip(), roots
    )
    return (
        {
            "path": state.normalized,
            "sha256": state.sha256,
            "size": state.size,
            "version_command": [state.normalized, "--version"],
            "version_output_sha256": sha256_bytes(version_output.encode("utf-8")),
            "version_output": version_output,
        },
        state,
    )


def driver_selection_records(
    command: Sequence[str],
    selected_states: Sequence[FileState],
    cwd: Path,
    roots: Sequence[Root],
) -> list[dict[str, object]]:
    """Prove which external tools a compiler driver selects for this command."""

    if not selected_states:
        return []
    if any(
        value == "-###" or value == "-save-temps" or value.startswith("-save-temps=")
        for value in command[1:]
    ):
        raise ProvenanceError(
            "driver-selection probing cannot compose with an existing "
            "-### or -save-temps option"
        )
    probe_command = [command[0], "-###", "-save-temps=obj", *command[1:]]
    completed = subprocess.run(
        probe_command,
        cwd=cwd,
        env=CHILD_ENVIRONMENT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise ProvenanceError(
            "driver-selection probe failed with exit status "
            f"{completed.returncode}"
        )

    selected_invocations: dict[Path, list[list[str]]] = {
        state.resolved: [] for state in selected_states
    }
    decoded = completed.stdout.decode("utf-8", errors="replace")
    for line in decoded.splitlines():
        candidate_line = line.lstrip()
        if not candidate_line.startswith('"'):
            continue
        try:
            invocation = shlex.split(candidate_line, posix=True)
        except ValueError as error:
            raise ProvenanceError(
                f"cannot parse driver-selection probe invocation: {line!r}"
            ) from error
        if not invocation:
            continue
        try:
            invoked_path = resolve_executable(invocation[0], cwd)
            invoked_resolved = invoked_path.resolve(strict=True)
        except ProvenanceError:
            continue
        if invoked_resolved in selected_invocations:
            selected_invocations[invoked_resolved].append(invocation)

    normalized_probe = [normalize(value, roots) for value in probe_command]
    normalized_output = normalize(decoded, roots)
    normalized_output_bytes = normalized_output.encode("utf-8")
    probe_digest = sha256_bytes(normalized_output_bytes)
    result: list[dict[str, object]] = []
    for selected in selected_states:
        invocations = selected_invocations[selected.resolved]
        if len(invocations) != 1:
            raise ProvenanceError(
                "driver-selection probe must contain exactly one invocation of "
                f"{selected.lexical}; observed {len(invocations)}"
            )
        result.append(
            {
                "driver": normalize(command[0], roots),
                "selected_executable": selected.normalized,
                "selected_executable_sha256": selected.sha256,
                "probe_command": normalized_probe,
                "probe_output": normalized_output,
                "probe_output_sha256": probe_digest,
                "probe_output_size": len(normalized_output_bytes),
                "selected_invocation": [
                    normalize(value, roots) for value in invocations[0]
                ],
            }
        )
    return result


def _split_make_words(value: str) -> list[str]:
    """Split the restricted Make dependency syntax emitted by Clang/GNU tools."""

    result: list[str] = []
    current: list[str] = []
    escaped = False
    for character in value:
        if escaped:
            if character not in {" ", "#", ":", "\\", "$"}:
                raise ProvenanceError(
                    f"unsupported dependency-file escape: \\{character}"
                )
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character.isspace():
            if current:
                result.append("".join(current))
                current = []
        else:
            current.append(character)
    if escaped:
        raise ProvenanceError("dependency file ends with an incomplete escape")
    if current:
        result.append("".join(current))
    return result


def parse_depfile_rule(path: Path) -> tuple[str, list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ProvenanceError(f"cannot read dependency file {path}: {error}") from error
    text = text.replace("\\\r\n", "").replace("\\\n", "")
    logical_lines = text.splitlines()
    if not logical_lines:
        raise ProvenanceError(f"dependency file is empty: {path}")
    first_rule = logical_lines[0]
    for extra_rule in logical_lines[1:]:
        if not extra_rule.strip():
            continue
        extra_separator = extra_rule.find(":")
        if extra_separator < 1:
            raise ProvenanceError(
                f"dependency file has an unsupported additional rule: {path}"
            )
        extra_targets = _split_make_words(extra_rule[:extra_separator])
        extra_dependencies = _split_make_words(extra_rule[extra_separator + 1 :])
        if len(extra_targets) != 1 or extra_dependencies:
            raise ProvenanceError(
                f"dependency file has a non-phony additional rule: {path}"
            )
    escaped = False
    separator = -1
    for index, character in enumerate(first_rule):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            separator = index
            break
    if separator < 1:
        raise ProvenanceError(f"dependency file has no target separator: {path}")
    targets = _split_make_words(first_rule[:separator])
    dependencies = _split_make_words(first_rule[separator + 1 :])
    if len(targets) != 1 or not dependencies:
        raise ProvenanceError(
            f"dependency file must contain one target and at least one input: {path}"
        )
    if len(dependencies) != len(set(dependencies)):
        raise ProvenanceError(f"dependency file contains duplicate inputs: {path}")
    return targets[0], dependencies


def parse_depfile(path: Path) -> list[str]:
    """Return inputs from one validated compiler/assembler/linker depfile."""

    return parse_depfile_rule(path)[1]


def states_by_resolved(states: Iterable[FileState]) -> dict[Path, FileState]:
    result: dict[Path, FileState] = {}
    for state in states:
        if state.resolved in result:
            previous = result[state.resolved]
            if previous.lexical != state.lexical:
                raise ProvenanceError(
                    "declared inputs contain aliases for one file: "
                    f"{previous.lexical} and {state.lexical}"
                )
            continue
        result[state.resolved] = state
    return result


def require_stable(
    before: dict[Path, FileState], cwd: Path, roots: Sequence[Root]
) -> None:
    for old in before.values():
        lexical = lexical_absolute(old.lexical, cwd)
        try:
            resolved = lexical.resolve(strict=True)
        except FileNotFoundError as error:
            raise ProvenanceError(
                f"build-step input disappeared during execution: {old.lexical}"
            ) from error
        if not resolved.is_file():
            raise ProvenanceError(
                f"build-step input stopped being a regular file: {old.lexical}"
            )
        if lexical.is_symlink() != old.leaf_symlink:
            raise ProvenanceError(
                "build-step input changed symbolic-link state during execution: "
                f"{old.lexical}"
            )
        _require_no_root_escape(
            lexical,
            resolved,
            roots,
            "build-step input",
            allow_leaf_symlink=old.leaf_symlink,
        )
        new = FileState(
            lexical=lexical,
            resolved=resolved,
            normalized=normalize(os.fspath(lexical), roots),
            sha256=sha256_file(resolved),
            size=resolved.stat().st_size,
            leaf_symlink=old.leaf_symlink,
        )
        if (
            new.resolved != old.resolved
            or new.sha256 != old.sha256
            or new.size != old.size
        ):
            raise ProvenanceError(f"build-step input changed during execution: {old.lexical}")


def atomic_record(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    if os.path.lexists(temporary):
        raise ProvenanceError(f"refusing stale temporary provenance record: {temporary}")
    data = json.dumps(value, indent=2, sort_keys=True) + "\n"
    published = False
    try:
        with temporary.open("x", encoding="utf-8", newline="") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
            published = True
        except FileExistsError as error:
            raise ProvenanceError(
                f"refusing concurrently created provenance record: {path}"
            ) from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            if not published:
                raise


def _reject_absolute_symlink_components(path: Path, description: str) -> None:
    absolute = lexical_absolute(path, Path.cwd())
    cursor = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        cursor /= component
        if os.path.lexists(cursor) and cursor.is_symlink():
            raise ProvenanceError(
                f"{description} has a symbolic-link component: {cursor}"
            )


def initialize_directory(path: Path) -> dict[str, object]:
    """Create one fresh provenance session without accepting stale contents."""

    directory = lexical_absolute(path, Path.cwd())
    _reject_absolute_symlink_components(directory, "provenance directory")
    if os.path.lexists(directory):
        if not directory.is_dir():
            raise ProvenanceError(
                f"provenance directory is not a real directory: {directory}"
            )
        if any(directory.iterdir()):
            raise ProvenanceError(
                f"provenance directory is not empty: {directory}"
            )
    else:
        directory.mkdir(parents=True)
        _reject_absolute_symlink_components(directory, "provenance directory")

    marker = directory / SESSION_MARKER
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": "mos-agondev-target-provenance-session",
        "fresh_directory_required": True,
        "session_id": uuid.uuid4().hex,
    }
    atomic_record(marker, document)
    observed = sorted(path.name for path in directory.iterdir())
    if observed != [SESSION_MARKER]:
        raise ProvenanceError(
            f"provenance directory changed during initialization: {directory}"
        )
    return document


def environment_record() -> dict[str, object]:
    return {
        "policy": "sanitized-deterministic-v1",
        "variables": dict(CHILD_ENVIRONMENT),
        "cleared_variables": list(CLEARED_ENVIRONMENT),
        "source_date_epoch": {
            "disposition": "cleared",
            "value": None,
        },
    }


def _remove_failed_outputs(paths: Iterable[Path], roots: Sequence[Root]) -> list[str]:
    failures: list[str] = []
    for path in paths:
        if not os.path.lexists(path):
            continue
        try:
            root = _owning_root(path, roots, "failed build output")
            _reject_symlink_components_below_root(path.parent, root, "failed build output")
            parent = path.parent.resolve(strict=True)
            if not _is_within(parent, Path(root.resolved)):
                raise ProvenanceError(
                    f"failed build output parent escapes root {root.name}: {path.parent}"
                )
            if path.is_dir() and not path.is_symlink():
                raise ProvenanceError(f"failed build output became a directory: {path}")
            path.unlink()
        except (OSError, ProvenanceError) as error:
            failures.append(f"{path}: {error}")
    return failures


def validate_producer_record(
    input_state: FileState,
    record_state: FileState,
    roots: Sequence[Root],
    recorder_state: FileState,
    session_state: FileState,
) -> dict[str, object]:
    try:
        document = json.loads(record_state.resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProvenanceError(
            f"cannot read producer record {record_state.lexical}: {error}"
        ) from error
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("evidence_kind") != "mos-agondev-actual-target-step"
    ):
        raise ProvenanceError(f"unsupported producer record: {record_state.lexical}")
    if document.get("step_kind") not in {
        "c-compile",
        "wrapped-assembly",
        "direct-assembly",
    }:
        raise ProvenanceError(
            f"producer record has an unsupported step kind: {record_state.lexical}"
        )
    if document.get("recorder") != recorder_state.record():
        raise ProvenanceError(
            f"producer record came from different recorder bytes: {record_state.lexical}"
        )
    if document.get("session") != session_state.record():
        raise ProvenanceError(
            f"producer record came from a different build session: {record_state.lexical}"
        )
    output = document.get("output")
    stability = document.get("input_stability")
    if not isinstance(output, dict) or stability != "verified-before-and-after":
        raise ProvenanceError(f"incomplete producer record: {record_state.lexical}")
    if output.get("path") != input_state.normalized:
        raise ProvenanceError(
            f"producer record output path mismatch for {input_state.lexical}: "
            f"{output.get('path')!r}"
        )
    if output.get("sha256") != input_state.sha256 or output.get("size") != input_state.size:
        raise ProvenanceError(
            f"producer record output digest mismatch for {input_state.lexical}"
        )
    return {
        "input": input_state.normalized,
        "record": record_state.normalized,
        "record_sha256": record_state.sha256,
        "output_sha256": input_state.sha256,
    }


def run_step(args: argparse.Namespace) -> dict[str, object]:
    cwd = lexical_absolute(args.cwd, Path.cwd())
    try:
        resolved_cwd = cwd.resolve(strict=True)
    except FileNotFoundError as error:
        raise ProvenanceError(f"working directory does not exist: {cwd}") from error
    if not resolved_cwd.is_dir():
        raise ProvenanceError(f"working directory is not a directory: {cwd}")
    roots = parse_roots(args.root, cwd)
    _require_no_root_escape(cwd, resolved_cwd, roots, "working directory")

    provenance_roots = [root for root in roots if root.name == "PROVENANCE"]
    if len(provenance_roots) != 1:
        raise ProvenanceError("exactly one PROVENANCE root is required")
    provenance_root = provenance_roots[0]
    _reject_absolute_symlink_components(
        Path(provenance_root.lexical), "PROVENANCE root"
    )
    session_state = regular_file_state(
        Path(provenance_root.lexical) / SESSION_MARKER,
        cwd,
        roots,
        "provenance session marker",
    )
    try:
        session_document = json.loads(
            session_state.resolved.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProvenanceError(
            f"cannot read provenance session marker: {session_state.lexical}"
        ) from error
    if (
        not isinstance(session_document, dict)
        or set(session_document) != {
            "schema_version",
            "evidence_kind",
            "fresh_directory_required",
            "session_id",
        }
        or session_document["schema_version"] != SCHEMA_VERSION
        or session_document["evidence_kind"]
        != "mos-agondev-target-provenance-session"
        or session_document["fresh_directory_required"] is not True
        or not isinstance(session_document["session_id"], str)
        or re.fullmatch(r"[0-9a-f]{32}", session_document["session_id"])
        is None
    ):
        raise ProvenanceError(
            f"invalid provenance session marker: {session_state.lexical}"
        )

    if not args.command:
        raise ProvenanceError("build step has no command after '--'")
    command = list(args.command)
    if command[:1] == ["--"]:
        command.pop(0)
    if not command:
        raise ProvenanceError("build step has no command after '--'")

    record_path = absent_file(args.record, cwd, roots, "provenance record")
    if _owning_root(record_path, roots, "provenance record").name != "PROVENANCE":
        raise ProvenanceError("provenance record must be inside the PROVENANCE root")
    output_path = absent_file(args.output, cwd, roots, "build output")
    depfile_path = absent_file(args.depfile, cwd, roots, "dependency file")
    secondary_paths = [
        absent_file(path, cwd, roots, "secondary build output")
        for path in args.secondary_output
    ]
    stdout_path = (
        absent_file(args.stdout_file, cwd, roots, "captured standard output")
        if args.stdout_file is not None
        else None
    )
    all_output_paths = [output_path, depfile_path, *secondary_paths]
    if stdout_path is not None:
        all_output_paths.append(stdout_path)
    if len(all_output_paths) != len(set(all_output_paths)):
        raise ProvenanceError("build step declares the same output path more than once")

    source_state = regular_file_state(args.source, cwd, roots, "primary source")
    declared_states = [source_state]
    declared_states.extend(
        regular_file_state(path, cwd, roots, "declared input") for path in args.input
    )

    recorder_state = regular_file_state(
        Path(__file__), cwd, roots, "provenance recorder"
    )
    declared_states.extend((recorder_state, session_state))

    response_states = [
        regular_file_state(path, cwd, roots, "response file")
        for path in args.response_file
    ]
    for state in response_states:
        try:
            response_bytes = state.resolved.read_bytes()
        except OSError as error:
            raise ProvenanceError(
                f"cannot read response file {state.lexical}: {error}"
            ) from error
        # Response-file tokenization is tool-specific. Version 1 binds a whole
        # argv-level @file but deliberately refuses recursive expansion rather
        # than pretending that an unparsed nested file is part of the closure.
        if b"@" in response_bytes:
            raise ProvenanceError(
                "nested response-file references are unsupported: "
                f"{state.lexical}"
            )
    command_response_paths: list[Path] = []
    for value in command[1:]:
        if "@" not in value:
            continue
        if not value.startswith("@") or value.count("@") != 1 or len(value) == 1:
            raise ProvenanceError(
                f"unsupported embedded or ambiguous response-file argument: {value!r}"
            )
        command_response_paths.append(
            regular_file_state(
                Path(value[1:]), cwd, roots, "command response file"
            ).resolved
        )
    declared_response_paths = [state.resolved for state in response_states]
    if command_response_paths != declared_response_paths:
        raise ProvenanceError(
            "command response files do not exactly match --response-file declarations"
        )
    if len(declared_response_paths) != len(set(declared_response_paths)):
        raise ProvenanceError("response files contain a duplicate file")
    declared_states.extend(response_states)

    executable_paths = [resolve_executable(command[0], cwd)]
    executable_paths.extend(resolve_executable(path, cwd) for path in args.nested_executable)
    command[0] = os.fspath(executable_paths[0])
    executable_records: list[dict[str, object]] = []
    executable_states: list[FileState] = []
    seen_executables: set[Path] = set()
    for executable in executable_paths:
        record, state = executable_record(executable, cwd, roots)
        if state.resolved in seen_executables:
            raise ProvenanceError(f"duplicate declared executable: {executable}")
        seen_executables.add(state.resolved)
        executable_records.append(record)
        executable_states.append(state)

    nested_states_by_resolved = {
        state.resolved: state for state in executable_states[1:]
    }
    driver_selected_states: list[FileState] = []
    for value in args.driver_selected_executable:
        selected_path = resolve_executable(value, cwd).resolve(strict=True)
        selected_state = nested_states_by_resolved.get(selected_path)
        if selected_state is None:
            raise ProvenanceError(
                "driver-selected executable must also be declared with "
                f"--nested-executable: {value}"
            )
        if selected_state in driver_selected_states:
            raise ProvenanceError(
                f"duplicate driver-selected executable: {selected_state.lexical}"
            )
        driver_selected_states.append(selected_state)
    driver_selection = driver_selection_records(
        command, driver_selected_states, cwd, roots
    )

    producer_records: list[dict[str, object]] = []
    producer_input_paths: set[Path] = set()
    producer_record_paths: set[Path] = set()
    for raw_input, raw_record in args.producer:
        input_state = regular_file_state(
            Path(raw_input), cwd, roots, "producer output"
        )
        record_state = regular_file_state(
            Path(raw_record), cwd, roots, "producer record"
        )
        if _owning_root(
            record_state.lexical, roots, "producer record"
        ).name != "PROVENANCE":
            raise ProvenanceError(
                f"producer record must be inside the PROVENANCE root: "
                f"{record_state.lexical}"
            )
        if input_state.resolved in producer_input_paths:
            raise ProvenanceError(
                f"producer declarations contain a duplicate input: "
                f"{input_state.lexical}"
            )
        if record_state.resolved in producer_record_paths:
            raise ProvenanceError(
                f"producer declarations contain a duplicate record: "
                f"{record_state.lexical}"
            )
        producer_input_paths.add(input_state.resolved)
        producer_record_paths.add(record_state.resolved)
        producer_records.append(
            validate_producer_record(
                input_state,
                record_state,
                roots,
                recorder_state,
                session_state,
            )
        )
        declared_states.append(input_state)
        declared_states.append(record_state)

    declared = states_by_resolved(declared_states)
    tools = states_by_resolved(executable_states)

    ordered_link_states: list[FileState] = []
    for path in args.link_input:
        state = regular_file_state(path, cwd, roots, "ordered link input")
        ordered_link_states.append(state)
        existing = declared.get(state.resolved)
        if existing is None:
            declared[state.resolved] = state
        elif existing.normalized != state.normalized:
            raise ProvenanceError(f"ordered link input uses an aliased path: {path}")
    if len({state.resolved for state in ordered_link_states}) != len(ordered_link_states):
        raise ProvenanceError("ordered link inputs contain a duplicate file")
    ordered_link_paths = {state.resolved for state in ordered_link_states}
    unrelated_producers = producer_input_paths - ordered_link_paths
    if unrelated_producers:
        unrelated = sorted(os.fspath(path) for path in unrelated_producers)
        raise ProvenanceError(
            "producer declarations contain inputs absent from the ordered link: "
            + ", ".join(unrelated)
        )

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=CHILD_ENVIRONMENT,
            check=False,
            stdout=subprocess.PIPE if stdout_path is not None else None,
        )
        if completed.returncode != 0:
            raise ProvenanceError(
                f"{args.kind} command failed with exit status {completed.returncode}"
            )
        if stdout_path is not None:
            assert completed.stdout is not None
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            with stdout_path.open("xb") as stream:
                stream.write(completed.stdout)

        require_stable(declared, cwd, roots)
        require_stable(tools, cwd, roots)

        output_state = regular_file_state(output_path, cwd, roots, "build output")
        depfile_state = regular_file_state(depfile_path, cwd, roots, "dependency file")
        secondary_states = [
            regular_file_state(path, cwd, roots, "secondary build output")
            for path in secondary_paths
        ]
        stdout_state = (
            regular_file_state(stdout_path, cwd, roots, "captured standard output")
            if stdout_path is not None
            else None
        )

        dependency_target, dependency_values = parse_depfile_rule(depfile_path)
        dependency_target_path = lexical_absolute(Path(dependency_target), cwd)
        if dependency_target_path != output_path:
            raise ProvenanceError(
                "dependency file target does not match build output: "
                f"{dependency_target_path} != {output_path}"
            )
        dependency_states: list[FileState] = []
        for value in dependency_values:
            state = regular_file_state(Path(value), cwd, roots, "dependency-file input")
            declared_state = declared.get(state.resolved)
            if declared_state is None:
                raise ProvenanceError(
                    "dependency file names an input that was not hashed before "
                    f"execution: {state.lexical}"
                )
            dependency_states.append(declared_state)
        dependency_resolved = {state.resolved for state in dependency_states}
        if source_state.resolved not in dependency_resolved:
            raise ProvenanceError("dependency file omits the primary source")
        for link_state in ordered_link_states:
            if link_state.resolved not in dependency_resolved:
                raise ProvenanceError(
                    f"dependency file omits ordered link input: {link_state.lexical}"
                )

        declared_records = [state.record() for state in declared.values()]
        declared_records.sort(key=lambda item: str(item["path"]))
        stability_digest = sha256_bytes(canonical_bytes(declared_records))
        record: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "evidence_kind": "mos-agondev-actual-target-step",
            "step_kind": args.kind,
            "input_stability": "verified-before-and-after",
            "working_directory": normalize(os.fspath(cwd), roots),
            "command": [normalize(value, roots) for value in command],
            "environment": environment_record(),
            "executables": executable_records,
            "driver_selection": driver_selection,
            "recorder": recorder_state.record(),
            "session": session_state.record(),
            "response_files": [state.record() for state in response_states],
            "source": source_state.record(),
            "declared_inputs": declared_records,
            "declared_inputs_sha256": stability_digest,
            "dependencies": [state.record() for state in dependency_states],
            "depfile": depfile_state.record(),
            "output": output_state.record(),
            "secondary_outputs": [state.record() for state in secondary_states],
            "captured_stdout": (
                stdout_state.record() if stdout_state is not None else None
            ),
            "ordered_link_inputs": [state.record() for state in ordered_link_states],
            "producer_records": producer_records,
        }
        absent_file(record_path, cwd, roots, "provenance record")
        atomic_record(record_path, record)
        return record
    except Exception as error:
        cleanup_failures = _remove_failed_outputs(all_output_paths, roots)
        if cleanup_failures:
            raise ProvenanceError(
                f"{error}; failed to remove untrusted outputs: "
                + "; ".join(cleanup_failures)
            ) from error
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", type=Path)
    parser.add_argument(
        "--kind",
        choices=(
            "c-compile",
            "c-assembly",
            "wrapped-assembly",
            "direct-assembly",
            "final-link",
        ),
    )
    parser.add_argument("--record", type=Path)
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--input", action="append", type=Path, default=[])
    parser.add_argument("--response-file", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--depfile", type=Path)
    parser.add_argument("--secondary-output", action="append", type=Path, default=[])
    parser.add_argument("--stdout-file", type=Path)
    parser.add_argument("--nested-executable", action="append", default=[])
    parser.add_argument(
        "--driver-selected-executable", action="append", default=[]
    )
    parser.add_argument("--link-input", action="append", type=Path, default=[])
    parser.add_argument(
        "--producer",
        action="append",
        nargs=2,
        metavar=("INPUT", "RECORD"),
        default=[],
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.initialize is not None:
            conflicting = any(
                value
                for value in (
                    args.kind,
                    args.record,
                    args.cwd,
                    args.root,
                    args.source,
                    args.input,
                    args.response_file,
                    args.output,
                    args.depfile,
                    args.secondary_output,
                    args.stdout_file,
                    args.nested_executable,
                    args.driver_selected_executable,
                    args.link_input,
                    args.producer,
                    args.command,
                )
            )
            if conflicting:
                raise ProvenanceError(
                    "--initialize cannot be combined with build-step arguments"
                )
            initialize_directory(args.initialize)
            print(f"initialized target provenance directory {args.initialize}")
            return 0
        missing = [
            name
            for name in ("kind", "record", "cwd", "source", "output", "depfile")
            if getattr(args, name) is None
        ]
        if missing:
            raise ProvenanceError(
                "build step is missing required arguments: " + ", ".join(missing)
            )
        record = run_step(args)
    except (OSError, ProvenanceError, subprocess.SubprocessError) as error:
        print(f"target provenance failed: {error}", file=sys.stderr)
        return 1
    print(
        f"recorded {record['step_kind']} provenance for "
        f"{record['output']['path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
