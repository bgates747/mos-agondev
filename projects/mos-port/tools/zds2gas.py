#!/usr/bin/env python3
"""Strict, deterministic ZDS-compatibility frontend for agon-mos assembly.

The maintained input remains close to the Zilog Developer Studio dialect.  The
generated output is GNU as source and is always disposable build output.  This
frontend deliberately translates a small, audited language instead of trying
to guess at arbitrary ZDS syntax.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Callable, Iterable, Sequence


FRONTEND_VERSION = 2
ANONYMOUS_LABEL_STRATEGY = "unique-symbol"
ASSEMBLY_SUFFIXES = frozenset({".asm", ".inc"})
PREPARATION_METADATA = ".mos-agondev-worktree.json"
PREPARATION_SCHEMA = 1
GIT_OBJECT_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")

IDENT = r"[A-Za-z_?][A-Za-z0-9_?]*"
MACRO_START_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<name>{IDENT}):?\s+MACRO(?:\s+(?P<params>.*?))?\s*$",
    re.IGNORECASE,
)
MACRO_END_RE = re.compile(r"^\s*(?:ENDMACRO|MACEND)\s*$", re.IGNORECASE)
SCOPE_RE = re.compile(r"^\s*SCOPE\s*$", re.IGNORECASE)
NAMED_LOCAL_DEF_RE = re.compile(rf"^\s*(?P<token>\$(?P<name>{IDENT})):")
NAMED_LOCAL_TOKEN_RE = re.compile(rf"(?<!\$)\$(?P<name>{IDENT})")
SUFFIX_LOCAL_DEF_RE = re.compile(r"^\s*(?P<token>(?P<name>[A-Za-z_][A-Za-z0-9_]*\?)):")
SUFFIX_LOCAL_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_?])(?P<name>[A-Za-z_][A-Za-z0-9_]*\?)(?![A-Za-z0-9_?])"
)
MACRO_LOCAL_DEF_RE = re.compile(rf"^\s*(?P<token>\$\$(?P<name>{IDENT})):")
MACRO_LOCAL_TOKEN_RE = re.compile(rf"\$\$(?P<name>{IDENT})")
ANON_DEF_RE = re.compile(r"^\s*\$\$:")
ANON_REF_RE = re.compile(r"\$(?P<direction>[FfBb])\b")
INCLUDE_RE = re.compile(r'^\s*INCLUDE\s+(?P<path>"[^"]+")\s*$', re.IGNORECASE)
END_RE = re.compile(r"^\s*END\s*$", re.IGNORECASE)
EQUATE_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<name>[A-Za-z_.$?][A-Za-z0-9_.$?]*):?\s+\.?(?:EQU)\s+(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
SET_RE = re.compile(
    rf"^(?P<indent>\s*)\.set\s+(?P<name>[A-Za-z_.$?][A-Za-z0-9_.$?]*)\s*,\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
STRUCT_START_RE = re.compile(
    rf"^\s*(?P<name>{IDENT})\s+\.STRUCT(?:\s+(?P<offset>[^\s]+))?\s*$",
    re.IGNORECASE,
)
STRUCT_RESERVE_RE = re.compile(
    rf"^\s*(?:(?P<member>{IDENT}):?\s+)?DS\s+(?P<count>.+?)\s*$",
    re.IGNORECASE,
)
STRUCT_TAG_RE = re.compile(
    rf"^\s*(?P<member>{IDENT}):?\s+\.TAG\s+(?P<tag>{IDENT})(?:\s+(?P<count>.+?))?\s*$",
    re.IGNORECASE,
)
STRUCT_END_RE = re.compile(
    rf"^\s*(?:(?P<size>{IDENT})\s+)?\.ENDSTRUCT(?:\s+(?P<tag>{IDENT}))?\s*$",
    re.IGNORECASE,
)


class FrontendError(Exception):
    """An input error with a stable code and original source location."""

    def __init__(self, source: str, line: int, code: str, message: str):
        self.source = source
        self.line = line
        self.code = code
        self.message = message
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.source}:{self.line}: error[{self.code}]: {self.message}"


@dataclasses.dataclass(frozen=True)
class MacroSpec:
    source_name: str
    gas_name: str
    params: tuple[str, ...]
    source: str
    line: int


@dataclasses.dataclass(frozen=True)
class LocalReference:
    token: str
    scope: int
    source: str
    line: int


@dataclasses.dataclass(frozen=True)
class SourceLocation:
    source: str
    line: int


@dataclasses.dataclass(frozen=True)
class EquateSpec:
    name: str
    canonical_value: str
    source: str
    line: int


@dataclasses.dataclass(frozen=True)
class StructureMember:
    name: str
    offset: int
    size: int
    source: str
    line: int


@dataclasses.dataclass(frozen=True)
class StructureSpec:
    name: str
    size_name: str | None
    size: int
    members: tuple[StructureMember, ...]
    source: str
    line: int


@dataclasses.dataclass(frozen=True)
class AnonymousReference:
    ordinal: int
    offset: int
    direction: str
    macro_name: str | None
    source: str
    line: int


@dataclasses.dataclass
class Analysis:
    source: str
    file_key: str
    macros: dict[str, MacroSpec]
    named_locals: dict[tuple[int, str], str]
    macro_locals: dict[tuple[str, str], str]
    anonymous_definitions: dict[int, str]
    anonymous_references: dict[tuple[int, int], str]
    duplicate_equates: set[int]
    equates: dict[str, EquateSpec]
    structures: dict[str, StructureSpec]
    structure_lines: dict[int, tuple[str, ...]]
    scopes: list[dict[str, object]]
    mappings: list[dict[str, object]]
    section_definitions: dict[str, dict[str, object]]
    line_sections: dict[int, tuple[str, str]]


@dataclasses.dataclass
class Translation:
    text: str
    analysis: Analysis
    output_to_source: list[int]
    output_locations: list[SourceLocation]
    transformations: dict[str, int]


@dataclasses.dataclass(frozen=True)
class ExpandedSource:
    text: str
    locations: tuple[SourceLocation, ...]
    includes: tuple[dict[str, object], ...]
    source_files: tuple[dict[str, str], ...]


@dataclasses.dataclass(frozen=True)
class PreparedProvenance:
    source_head: str
    tracked_dirty: bool
    metadata_sha256: str
    prepared_file_count: int

    @property
    def identity(self) -> str:
        suffix = "+tracked-dirty" if self.tracked_dirty else ""
        return f"{self.source_head}{suffix}"


def split_physical_line(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n") or line.endswith("\r"):
        return line[:-1], line[-1]
    return line, ""


def split_comment(line: str) -> tuple[str, str]:
    """Split at a semicolon outside single- and double-quoted strings."""

    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote is not None:
            escaped = True
            continue
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == ";":
            return line[:index], line[index:]
    return line, ""


def map_unquoted(text: str, transform: Callable[[str], str]) -> str:
    """Apply *transform* only to regions outside quoted strings."""

    output: list[str] = []
    plain: list[str] = []
    quote: str | None = None
    quoted: list[str] = []
    escaped = False

    def flush_plain() -> None:
        if plain:
            output.append(transform("".join(plain)))
            plain.clear()

    for char in text:
        if quote is None:
            if char in {"'", '"'}:
                flush_plain()
                quote = char
                quoted = [char]
            else:
                plain.append(char)
            continue

        quoted.append(char)
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            output.append("".join(quoted))
            quoted = []
            quote = None

    if quote is not None:
        # The assembler will diagnose the unterminated literal.  Keeping it
        # verbatim avoids a misleading token rewrite before that diagnostic.
        output.append("".join(quoted))
    flush_plain()
    return "".join(output)


def mask_quoted(text: str) -> str:
    return _mask_quoted(text)


def _mask_quoted(text: str) -> str:
    chars = list(text)
    quote: str | None = None
    escaped = False
    for index, char in enumerate(chars):
        if quote is None:
            if char in {"'", '"'}:
                quote = char
                chars[index] = " "
        else:
            chars[index] = " "
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
    return "".join(chars)


def parse_params(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return ()
    params = tuple(part.strip() for part in raw.split(","))
    if any(not re.fullmatch(IDENT, param) for param in params):
        raise ValueError(f"unsupported macro parameter list: {raw!r}")
    if len(params) != len(set(params)):
        raise ValueError(f"duplicate macro parameter in: {raw!r}")
    return params


def safe_identifier(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", lambda match: f"_{ord(match.group()):02x}_", value)
    if not value or value[0].isdigit():
        value = f"z_{value}"
    return value


def macro_gas_name(source_name: str) -> str:
    return f"zds_{safe_identifier(source_name)}"


def file_key(source_name: str) -> str:
    normalized = PurePosixPath(source_name.replace("\\", "/")).as_posix()
    readable = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_").lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{readable or 'source'}_{digest}"


def discover_macros(sources: Sequence[tuple[str, str]]) -> dict[str, MacroSpec]:
    macros: dict[str, MacroSpec] = {}
    for source_name, text in sources:
        active: MacroSpec | None = None
        for line_number, physical in enumerate(text.splitlines(keepends=True), 1):
            line, _ = split_physical_line(physical)
            code, _ = split_comment(line)
            masked = mask_quoted(code)
            start = MACRO_START_RE.match(masked)
            if start:
                if active is not None:
                    raise FrontendError(
                        source_name, line_number, "nested-macro", "nested macro definitions are unsupported"
                    )
                try:
                    params = parse_params(start.group("params"))
                except ValueError as error:
                    raise FrontendError(source_name, line_number, "macro-params", str(error)) from error
                source_macro = start.group("name")
                key = source_macro
                spec = MacroSpec(
                    source_name=source_macro,
                    gas_name=macro_gas_name(source_macro),
                    params=params,
                    source=source_name,
                    line=line_number,
                )
                previous = macros.get(key)
                if previous is not None:
                    raise FrontendError(
                        source_name,
                        line_number,
                        "duplicate-macro",
                        f"macro {source_macro!r} was already defined at {previous.source}:{previous.line}",
                    )
                macros[key] = spec
                active = spec
            elif MACRO_END_RE.match(masked):
                if active is None:
                    raise FrontendError(
                        source_name, line_number, "orphan-macro-end", "macro terminator without a macro definition"
                    )
                active = None
        if active is not None:
            raise FrontendError(
                source_name, active.line, "unterminated-macro", f"macro {active.source_name!r} has no terminator"
            )
    return macros


def canonical_equate_value(value: str) -> str:
    """Canonicalize spelling, while retaining case-sensitive symbol names."""

    normalized = rewrite_literals_and_locations(value)
    normalized = re.sub(
        r"0[xX]([0-9A-Fa-f]+)", lambda match: f"0x{match.group(1).lower()}", normalized
    )
    normalized = re.sub(r"0[bB]([01]+)", lambda match: f"0b{match.group(1)}", normalized)
    return re.sub(r"\s+", "", normalized)


def parse_absolute_integer(value: str, location: SourceLocation, purpose: str) -> int:
    normalized = rewrite_literals_and_locations(value.strip())
    if not re.fullmatch(r"(?:0[xX][0-9A-Fa-f]+|0[bB][01]+|[0-9]+)", normalized):
        raise FrontendError(
            location.source,
            location.line,
            "nonconstant-structure-size",
            f"{purpose} requires a non-negative integer literal, got {value!r}",
        )
    result = int(normalized, 0)
    if result < 0:
        raise FrontendError(
            location.source,
            location.line,
            "negative-structure-size",
            f"{purpose} cannot be negative",
        )
    return result


def parse_section_definition(masked: str) -> tuple[str, dict[str, object]] | None:
    match = re.match(r"^\s*DEFINE\s+([^,\s]+)\s*,\s*SPACE\s*=\s*(ROM|RAM)(?P<tail>.*)$", masked, re.I)
    if not match:
        return None
    name = match.group(1)
    definition: dict[str, object] = {"space": match.group(2).upper()}
    align = re.search(r",\s*ALIGN\s*=\s*([^,\s]+)", match.group("tail"), re.I)
    if align:
        definition["align"] = align.group(1)
    return name, definition


def analyze(
    source_name: str,
    text: str,
    macros: dict[str, MacroSpec],
    locations: Sequence[SourceLocation] | None = None,
) -> Analysis:
    key = file_key(source_name)
    named_locals: dict[tuple[int, str], str] = {}
    macro_locals: dict[tuple[str, str], str] = {}
    named_refs: list[LocalReference] = []
    macro_refs: list[tuple[str, str, SourceLocation]] = []
    anonymous_defs: list[tuple[int, str | None, str]] = []
    anonymous_refs: list[AnonymousReference] = []
    anonymous_definitions: dict[int, str] = {}
    anonymous_references: dict[tuple[int, int], str] = {}
    duplicate_equates: set[int] = set()
    equates: dict[str, EquateSpec] = {}
    structures: dict[str, StructureSpec] = {}
    structure_lines: dict[int, tuple[str, ...]] = {}
    scopes: list[dict[str, object]] = [
        {
            "ordinal": 0,
            "source": source_name,
            "line": 1,
            "explicit": False,
            "name": "implicit-file-scope",
        }
    ]
    mappings: list[dict[str, object]] = []
    section_definitions: dict[str, dict[str, object]] = {}
    line_sections: dict[int, tuple[str, str]] = {}
    current_section = ".text"
    current_space = "ROM"
    scope = 0
    active_macro: MacroSpec | None = None
    active_structure_name: str | None = None
    active_structure_start: SourceLocation | None = None
    active_structure_offset = 0
    active_structure_members: list[StructureMember] = []

    physical_lines = text.splitlines(keepends=True)
    if locations is None:
        locations = [SourceLocation(source_name, line) for line in range(1, len(physical_lines) + 1)]
    if len(locations) != len(physical_lines):
        raise ValueError("source-location map does not match the expanded input")

    for ordinal, (physical, location) in enumerate(zip(physical_lines, locations), 1):
        line, _ = split_physical_line(physical)
        code, _ = split_comment(line)
        masked = mask_quoted(code)

        structure_start = STRUCT_START_RE.match(masked)
        if structure_start:
            if active_structure_name is not None:
                raise FrontendError(
                    location.source,
                    location.line,
                    "nested-structure",
                    "nested .STRUCT definitions are unsupported",
                )
            structure_name = structure_start.group("name")
            if structure_name in structures:
                prior = structures[structure_name]
                raise FrontendError(
                    location.source,
                    location.line,
                    "duplicate-structure",
                    f"structure {structure_name!r} was already defined at {prior.source}:{prior.line}",
                )
            active_structure_name = structure_name
            active_structure_start = location
            active_structure_offset = (
                parse_absolute_integer(
                    structure_start.group("offset"), location, ".STRUCT starting offset"
                )
                if structure_start.group("offset")
                else 0
            )
            active_structure_members = []
            structure_lines[ordinal] = (f"; zds2gas: .STRUCT {structure_name}",)
            continue

        if active_structure_name is not None:
            if not masked.strip():
                structure_lines[ordinal] = (code,)
                continue
            end = STRUCT_END_RE.match(masked)
            if end:
                closing_tag = end.group("tag")
                if closing_tag is not None and closing_tag != active_structure_name:
                    raise FrontendError(
                        location.source,
                        location.line,
                        "structure-name-mismatch",
                        f".ENDSTRUCT names {closing_tag!r}, expected {active_structure_name!r}",
                    )
                size_name = end.group("size")
                assert active_structure_start is not None
                spec = StructureSpec(
                    active_structure_name,
                    size_name,
                    active_structure_offset,
                    tuple(active_structure_members),
                    active_structure_start.source,
                    active_structure_start.line,
                )
                structures[active_structure_name] = spec
                rendered: list[str] = []
                if size_name:
                    rendered.append(f".equiv {size_name}, {active_structure_offset}")
                rendered.append(
                    f"; zds2gas: .ENDSTRUCT {active_structure_name} ({active_structure_offset} bytes)"
                )
                structure_lines[ordinal] = tuple(rendered)
                active_structure_name = None
                active_structure_start = None
                active_structure_members = []
                continue

            reserve = STRUCT_RESERVE_RE.match(masked)
            tag = STRUCT_TAG_RE.match(masked)
            if reserve:
                member_name = reserve.group("member")
                member_size = parse_absolute_integer(
                    reserve.group("count"), location, "structure DS count"
                )
            elif tag:
                member_name = tag.group("member")
                referenced = structures.get(tag.group("tag"))
                if referenced is None:
                    raise FrontendError(
                        location.source,
                        location.line,
                        "unknown-structure-tag",
                        f".TAG references undefined case-exact structure {tag.group('tag')!r}",
                    )
                repetitions = (
                    parse_absolute_integer(tag.group("count"), location, ".TAG count")
                    if tag.group("count")
                    else 1
                )
                member_size = referenced.size * repetitions
            else:
                raise FrontendError(
                    location.source,
                    location.line,
                    "unsupported-structure-member",
                    f"only DS and .TAG are supported in .STRUCT, got {masked.strip()!r}",
                )

            rendered = []
            if member_name:
                if any(member.name == member_name for member in active_structure_members):
                    raise FrontendError(
                        location.source,
                        location.line,
                        "duplicate-structure-member",
                        f"member {member_name!r} occurs twice in {active_structure_name}",
                    )
                member = StructureMember(
                    member_name, active_structure_offset, member_size, location.source, location.line
                )
                active_structure_members.append(member)
                rendered.append(
                    f".equiv {active_structure_name}.{member_name}, {active_structure_offset}"
                )
            rendered.append(
                f"; zds2gas: {masked.strip()} ({member_size} bytes, no allocation)"
            )
            structure_lines[ordinal] = tuple(rendered)
            active_structure_offset += member_size
            continue

        start = MACRO_START_RE.match(masked)
        if start:
            if active_macro is not None:
                raise FrontendError(
                    location.source, location.line, "nested-macro", "nested macros are unsupported"
                )
            active_macro = macros[start.group("name")]
            continue
        if MACRO_END_RE.match(masked):
            if active_macro is None:
                raise FrontendError(
                    location.source, location.line, "orphan-macro-end", "macro terminator without macro"
                )
            active_macro = None
            continue

        if SCOPE_RE.match(masked):
            if active_macro is not None:
                raise FrontendError(
                    location.source, location.line, "scope-in-macro", "SCOPE inside a macro is unsupported"
                )
            scope += 1
            scopes.append(
                {
                    "ordinal": scope,
                    "source": location.source,
                    "line": location.line,
                    "explicit": True,
                    "name": f"scope-{scope}",
                }
            )
            continue

        section_definition = parse_section_definition(masked)
        if section_definition is not None:
            name, definition = section_definition
            prior = section_definitions.get(name.casefold())
            if prior is not None and prior != {"name": name, **definition}:
                raise FrontendError(
                    location.source,
                    location.line,
                    "section-redefinition",
                    f"conflicting DEFINE for section {name!r}",
                )
            section_definitions[name.casefold()] = {"name": name, **definition}

        segment = re.match(r"^\s*SEGMENT\s+([^\s]+)\s*$", masked, re.I)
        section = re.match(r"^\s*SECTION\s+([^\s]+)\s*$", masked, re.I)
        if segment:
            source_section = segment.group(1)
            known = source_section.casefold()
            current_section = {"text": ".text", "data": ".data", "bss": ".bss"}.get(
                known, source_section
            )
            definition = section_definitions.get(known, {})
            current_space = "RAM" if known in {"bss", "data"} else str(
                definition.get("space", "ROM")
            ).upper()
        elif section:
            source_section = section.group(1)
            known = source_section.casefold()
            current_section = {"text": ".text", "data": ".data", "bss": ".bss"}.get(
                known, source_section
            )
            current_space = "RAM" if known in {"bss", "data"} else "ROM"
        line_sections[ordinal] = (current_section, current_space)

        equate = EQUATE_RE.match(code) or SET_RE.match(code)
        if equate:
            equate_name = equate.group("name")
            canonical = canonical_equate_value(equate.group("value"))
            prior = equates.get(equate_name)
            if prior is None:
                equates[equate_name] = EquateSpec(
                    equate_name, canonical, location.source, location.line
                )
            elif prior.canonical_value == canonical:
                duplicate_equates.add(ordinal)
            else:
                raise FrontendError(
                    location.source,
                    location.line,
                    "conflicting-equate",
                    f"immutable symbol {equate_name!r} was first defined as "
                    f"{prior.canonical_value!r} at {prior.source}:{prior.line}, not {canonical!r}",
                )

        if active_macro is not None:
            definition = MACRO_LOCAL_DEF_RE.match(masked)
            if definition:
                local_name = definition.group("name")
                local_key = (active_macro.source_name, local_name)
                if local_key in macro_locals:
                    raise FrontendError(
                        location.source,
                        location.line,
                        "duplicate-macro-local",
                        f"macro-local $${local_name} is defined more than once in {active_macro.source_name}",
                    )
                generated = (
                    f".Lzds_m_{safe_identifier(active_macro.source_name)}_"
                    f"{safe_identifier(local_name)}\\@"
                )
                macro_locals[local_key] = generated
                mappings.append(
                    {
                        "kind": "macro-local",
                        "source": f"$${local_name}",
                        "generated": generated,
                        "defined_in": location.source,
                        "line": location.line,
                        "macro": active_macro.source_name,
                    }
                )
            for token in MACRO_LOCAL_TOKEN_RE.finditer(masked):
                macro_refs.append((active_macro.source_name, token.group("name"), location))
        elif MACRO_LOCAL_TOKEN_RE.search(masked):
            raise FrontendError(
                location.source,
                location.line,
                "macro-local-outside-macro",
                "$$name is only valid inside a macro",
            )

        dollar_definition = NAMED_LOCAL_DEF_RE.match(masked)
        suffix_definition = SUFFIX_LOCAL_DEF_RE.match(masked)
        if active_macro is not None and (dollar_definition or suffix_definition):
            token = (dollar_definition or suffix_definition).group("token")
            raise FrontendError(
                location.source,
                location.line,
                "scoped-local-in-macro",
                f"scoped local {token!r} in a macro is invocation-unsafe; use $$name",
            )

        for definition in (dollar_definition, suffix_definition):
            if definition is None:
                continue
            local_token = definition.group("token")
            local_key = (scope, local_token)
            if local_key in named_locals:
                raise FrontendError(
                    location.source,
                    location.line,
                    "duplicate-local",
                    f"local {local_token} is defined more than once in scope {scope}",
                )
            generated = f".Lzds_{key}_s{scope:03d}_{safe_identifier(local_token)}"
            named_locals[local_key] = generated
            mappings.append(
                {
                    "kind": "named-local",
                    "source": local_token,
                    "generated": generated,
                    "defined_in": location.source,
                    "line": location.line,
                    "scope": scope,
                }
            )

        for token in NAMED_LOCAL_TOKEN_RE.finditer(masked):
            name = token.group("name")
            if name.casefold() not in {"f", "b"}:
                named_refs.append(
                    LocalReference(f"${name}", scope, location.source, location.line)
                )

        invocation = re.match(
            rf"^\s*(?:(?:[A-Za-z_.$?][A-Za-z0-9_.$?]*):\s*)?"
            rf"(?P<op>{IDENT})(?P<rest>.*)$",
            masked,
        )
        invoked_name = invocation.group("op") if invocation else None
        for token in SUFFIX_LOCAL_TOKEN_RE.finditer(masked):
            if invoked_name == token.group("name") and invoked_name in macros:
                continue
            named_refs.append(
                LocalReference(token.group("name"), scope, location.source, location.line)
            )

        macro_context = active_macro.source_name if active_macro is not None else None
        if ANON_DEF_RE.match(masked):
            serial = len(anonymous_defs) + 1
            if active_macro is None:
                generated = f".Lzds_{key}_a{serial:04d}"
            else:
                generated = (
                    f".Lzds_m_{safe_identifier(active_macro.source_name)}_a{serial:04d}\\@"
                )
            anonymous_defs.append((ordinal, macro_context, generated))
            anonymous_definitions[ordinal] = generated
            mappings.append(
                {
                    "kind": "anonymous",
                    "source": "$$",
                    "generated": generated,
                    "defined_in": location.source,
                    "line": location.line,
                    "macro": macro_context,
                }
            )
        for occurrence, token in enumerate(ANON_REF_RE.finditer(masked)):
            anonymous_refs.append(
                AnonymousReference(
                    ordinal,
                    occurrence,
                    token.group("direction").casefold(),
                    macro_context,
                    location.source,
                    location.line,
                )
            )

    for reference in named_refs:
        if (reference.scope, reference.token) not in named_locals:
            raise FrontendError(
                reference.source,
                reference.line,
                "unresolved-local",
                f"local {reference.token} has no case-exact definition in scope {reference.scope}",
            )
    for macro_name, local_name, location in macro_refs:
        if (macro_name, local_name) not in macro_locals:
            raise FrontendError(
                location.source,
                location.line,
                "unresolved-macro-local",
                f"macro-local $${local_name} has no case-exact definition in macro {macro_name}",
            )
    for reference in anonymous_refs:
        candidates = [
            candidate
            for candidate in anonymous_defs
            if candidate[1] == reference.macro_name
            and (
                candidate[0] > reference.ordinal
                if reference.direction == "f"
                else candidate[0] < reference.ordinal
            )
        ]
        if not candidates:
            raise FrontendError(
                reference.source,
                reference.line,
                "unresolved-anonymous",
                f"${reference.direction.upper()} has no "
                f"{'following' if reference.direction == 'f' else 'preceding'} $$ label",
            )
        target = min(candidates, key=lambda item: item[0]) if reference.direction == "f" else max(
            candidates, key=lambda item: item[0]
        )
        anonymous_references[(reference.ordinal, reference.offset)] = target[2]

    if active_structure_name is not None:
        assert active_structure_start is not None
        raise FrontendError(
            active_structure_start.source,
            active_structure_start.line,
            "unterminated-structure",
            f"structure {active_structure_name!r} has no .ENDSTRUCT",
        )

    return Analysis(
        source=source_name,
        file_key=key,
        macros=macros,
        named_locals=named_locals,
        macro_locals=macro_locals,
        anonymous_definitions=anonymous_definitions,
        anonymous_references=anonymous_references,
        duplicate_equates=duplicate_equates,
        equates=equates,
        structures=structures,
        structure_lines=structure_lines,
        scopes=scopes,
        mappings=mappings,
        section_definitions=section_definitions,
        line_sections=line_sections,
    )


def replace_macro_params(code: str, macro: MacroSpec) -> str:
    def transform(segment: str) -> str:
        for param in sorted(macro.params, key=len, reverse=True):
            # ZDS concatenates tokens as PREFIX&PARAM&SUFFIX.  GAS requires a
            # parameter escape and an explicit end-of-name marker.
            segment = re.sub(
                rf"&{re.escape(param)}&",
                lambda _: f"\\{param}\\()",
                segment,
            )
        for param in sorted(macro.params, key=len, reverse=True):
            segment = re.sub(
                rf"(?<![A-Za-z0-9_?\\]){re.escape(param)}(?![A-Za-z0-9_?])",
                lambda _: f"\\{param}",
                segment,
            )
        return segment

    return map_unquoted(code, transform)


def rewrite_macro_invocation(code: str, macros: dict[str, MacroSpec]) -> tuple[str, bool]:
    match = re.match(
        rf"^(?P<prefix>\s*(?:(?:[A-Za-z_.$?][A-Za-z0-9_.$?]*):\s*)?)"
        rf"(?P<op>{IDENT})(?P<rest>.*)$",
        code,
    )
    if not match:
        return code, False
    spec = macros.get(match.group("op"))
    if spec is None:
        return code, False
    rest = match.group("rest")
    stripped = rest.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        leading = rest[: len(rest) - len(rest.lstrip())]
        rest = f"{leading or ' '}{stripped[1:-1]}"
    elif rest and not rest[0].isspace():
        return code, False
    return f"{match.group('prefix')}{spec.gas_name}{rest}", True


def rewrite_directive(code: str, analysis: Analysis, line_number: int) -> tuple[str, str | None]:
    """Rewrite one leading directive and return its transformation category."""

    indent = re.match(r"^\s*", code).group()
    stripped = code.strip()
    if not stripped:
        return code, None
    if SCOPE_RE.match(code):
        return f"{indent}; zds2gas: {stripped}", "scope"
    if re.match(r"^\s*DEFINE\b", code, re.I):
        return f"{indent}; zds2gas: {stripped}", "define"
    if re.match(r"^\s*END\s*$", code, re.I):
        return f"{indent}; zds2gas: END", "end"

    equate = EQUATE_RE.match(code) or SET_RE.match(code)
    if equate:
        if line_number in analysis.duplicate_equates:
            return (
                f"{equate.group('indent')}; zds2gas: duplicate immutable EQU "
                f"{equate.group('name')} = {equate.group('value')}",
                "duplicate-equ",
            )
        return (
            f"{equate.group('indent')}.equiv {equate.group('name')}, {equate.group('value')}",
            "equ",
        )

    segment = re.match(r"^(?P<indent>\s*)SEGMENT\s+(?P<name>[^\s]+)\s*$", code, re.I)
    if segment:
        name = segment.group("name")
        definition = analysis.section_definitions.get(name.casefold(), {})
        known = name.casefold()
        if known == "bss":
            return f"{segment.group('indent')}.section .bss,\"aw\",@nobits", "segment"
        if known == "data":
            return f"{segment.group('indent')}.section .data,\"aw\",@progbits", "segment"
        if str(definition.get("space", "")).upper() == "RAM":
            return f"{segment.group('indent')}.section {name},\"aw\",@nobits", "segment"
        return f"{segment.group('indent')}.section {name},\"ax\",@progbits", "segment"

    section = re.match(r"^(?P<indent>\s*)SECTION\s+(?P<name>[^\s]+)\s*$", code, re.I)
    if section:
        section_name = section.group("name").casefold()
        names = {"text": ".text", "data": ".data", "bss": ".bss"}
        gas_section = names.get(section_name, section.group("name"))
        if section_name == "bss":
            return f"{section.group('indent')}.section {gas_section},\"aw\",@nobits", "section"
        return f"{section.group('indent')}.section {gas_section}", "section"

    include = re.match(r'^(?P<indent>\s*)INCLUDE\s+(?P<path>"[^"]+")\s*$', code, re.I)
    if include:
        include_path = include.group("path")
        if include_path[1:-1].casefold() == "ez80f92.inc":
            include_path = '"ez80f92.inc"'
        return f"{include.group('indent')}.include {include_path}", "include"

    replacements = {
        "IF": ".if",
        "ELSE": ".else",
        "ENDIF": ".endif",
        "ERROR": '.error "ZDS ERROR directive reached"',
        "DL": "d32",
        "DW24": "d24",
    }
    match = re.match(
        rf"^(?P<prefix>\s*(?:(?:[A-Za-z_.$?][A-Za-z0-9_.$?]*):\s*)?)"
        rf"(?P<op>{'|'.join(replacements)})(?P<rest>(?:\s+.*)?\s*)$",
        code,
        re.I,
    )
    if match:
        op = match.group("op").upper()
        return f"{match.group('prefix')}{replacements[op]}{match.group('rest')}", op.casefold()

    reserve = re.match(
        r"^(?P<prefix>\s*(?:(?:[A-Za-z_.$?][A-Za-z0-9_.$?]*):?\s+)?)"
        r"DS\s+(?P<count>.+?)\s*$",
        code,
        re.I,
    )
    if reserve:
        _, space = analysis.line_sections.get(line_number, (".text", "ROM"))
        fill = ", 0xff" if space == "ROM" else ""
        return f"{reserve.group('prefix')}.skip {reserve.group('count')}{fill}", "reserve"
    return code, None


def rewrite_literals_and_locations(code: str) -> str:
    def transform(segment: str) -> str:
        segment = re.sub(r"(?<![A-Za-z0-9_])%([0-9A-Fa-f]+)\b", r"0x\1", segment)
        segment = re.sub(r"(?<![A-Za-z0-9_])([0-9A-Fa-f]+)[hH]\b", r"0x\1", segment)
        segment = re.sub(r"(?<![A-Za-z0-9_])([01]+)[bB]\b", r"0b\1", segment)
        segment = re.sub(r"\$(?![$A-Za-z_?])", ".", segment)
        return segment

    return map_unquoted(code, transform)


def rewrite_implicit_label(code: str, macros: dict[str, MacroSpec]) -> tuple[str, bool]:
    """Add the colon ZDS permits between a column-zero label and its opcode."""

    match = re.match(
        rf"^(?P<label>[A-Za-z_.$?][A-Za-z0-9_.$?]*)"
        rf"(?P<space>\s+)(?P<op>{IDENT})(?P<rest>(?:\s+.*)?\s*)$",
        code,
    )
    if not match:
        return code, False
    source_op = match.group("op")
    known_after_label = {
        "db", "dw", "dl", "dw24", "ds", "jp", "jr", "call", "ld", "section"
    }
    if source_op.casefold() not in known_after_label and source_op not in macros:
        return code, False
    return (
        f"{match.group('label')}:{match.group('space')}{match.group('op')}{match.group('rest')}",
        True,
    )


def rewrite_alu_parentheses(code: str) -> tuple[str, bool]:
    """Avoid GAS treating a doubly-parenthesized ALU constant as an operand."""

    match = re.match(
        r"^(?P<head>\s*(?:(?:[A-Za-z_.$?][A-Za-z0-9_.$?]*|[0-9]+):\s*)?"
        r"(?:ADC|ADD|AND|CP|OR|SBC|SUB|TST|XOR)\s+[^,]+,\s*)"
        r"\((?P<expression>\(.*\))\)(?P<tail>\s*)$",
        code,
        re.I,
    )
    if not match:
        return code, False
    return f"{match.group('head')}{match.group('expression')}{match.group('tail')}", True


def rewrite_locals(
    code: str, analysis: Analysis, scope: int, macro: MacroSpec | None, line_number: int
) -> str:
    anonymous_occurrence = 0

    def transform(segment: str) -> str:
        nonlocal anonymous_occurrence
        if macro is not None:
            def macro_local(match: re.Match[str]) -> str:
                key = (macro.source_name, match.group("name"))
                return analysis.macro_locals[key]

            segment = MACRO_LOCAL_TOKEN_RE.sub(macro_local, segment)
        definition = analysis.anonymous_definitions.get(line_number)
        if definition is not None:
            segment = re.sub(
                r"^\s*\$\$:", lambda match: match.group().replace("$$", definition), segment
            )

        def anonymous_reference(_: re.Match[str]) -> str:
            nonlocal anonymous_occurrence
            key = (line_number, anonymous_occurrence)
            anonymous_occurrence += 1
            return analysis.anonymous_references[key]

        segment = ANON_REF_RE.sub(anonymous_reference, segment)

        def named_local(match: re.Match[str]) -> str:
            name = match.group("name")
            if name.casefold() in {"f", "b"}:
                return match.group()
            return analysis.named_locals[(scope, f"${name}")]

        segment = NAMED_LOCAL_TOKEN_RE.sub(named_local, segment)

        def suffix_local(match: re.Match[str]) -> str:
            return analysis.named_locals[(scope, match.group("name"))]

        segment = SUFFIX_LOCAL_TOKEN_RE.sub(suffix_local, segment)
        return segment

    return map_unquoted(code, transform)


def split_wide_register_copy(code: str) -> tuple[list[str], bool]:
    match = re.match(
        r"^(?P<prefix>\s*(?:(?:[A-Za-z_.$][A-Za-z0-9_.$]*|[0-9]+):\s*)?)"
        r"LD\s+(?P<dst>BC|DE|HL|IX|IY)\s*,\s*(?P<src>BC|DE|HL|IX|IY)\s*$",
        code,
        re.I,
    )
    if not match or match.group("dst").casefold() == match.group("src").casefold():
        return [code], False
    prefix = match.group("prefix")
    second_indent = re.match(r"^\s*", prefix).group()
    return [
        f"{prefix}push {match.group('src').lower()}",
        f"{second_indent}pop {match.group('dst').lower()}",
    ], True


def translate(
    source_name: str,
    text: str,
    macros: dict[str, MacroSpec] | None = None,
    locations: Sequence[SourceLocation] | None = None,
    input_identity: str = "unversioned-single-file",
) -> Translation:
    physical_lines = text.splitlines(keepends=True)
    if text and not physical_lines:
        physical_lines = [text]
    if locations is None:
        locations = [SourceLocation(source_name, line) for line in range(1, len(physical_lines) + 1)]
        end_index = next(
            (
                index
                for index, physical in enumerate(physical_lines)
                if END_RE.match(mask_quoted(split_comment(split_physical_line(physical)[0])[0]))
            ),
            None,
        )
        if end_index is not None:
            physical_lines = physical_lines[: end_index + 1]
            locations = locations[: end_index + 1]
            text = "".join(physical_lines)
    elif len(locations) != len(physical_lines):
        raise ValueError("source-location map does not match the translated input")

    if macros is None:
        macros = discover_macros([(source_name, text)])
    analysis = analyze(source_name, text, macros, locations)
    transformations: dict[str, int] = {}
    provenance_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    output: list[str] = [
        f"; generated by zds2gas frontend schema {FRONTEND_VERSION}\n",
        f"; translation unit: {source_name}\n",
        f"; agon-mos input identity: {input_identity}\n",
        f"; expanded input sha256: {provenance_digest}\n",
        "; DO NOT EDIT: generated build input\n",
    ]
    header_location = locations[0] if locations else SourceLocation(source_name, 1)
    output_to_source: list[int] = [header_location.line] * len(output)
    output_locations: list[SourceLocation] = [header_location] * len(output)
    scope = 0
    active_macro: MacroSpec | None = None

    def count(category: str) -> None:
        transformations[category] = transformations.get(category, 0) + 1

    for line_number, (physical, location) in enumerate(zip(physical_lines, locations), 1):
        line, newline = split_physical_line(physical)
        code, comment = split_comment(line)
        masked = mask_quoted(code)
        start = MACRO_START_RE.match(masked)

        structure_rendered = analysis.structure_lines.get(line_number)
        if structure_rendered is not None:
            rendered_lines = list(structure_rendered)
            count("structure")
        elif start:
            active_macro = macros[start.group("name")]
            params = ",".join(active_macro.params)
            replacement = f"{start.group('indent')}.macro {active_macro.gas_name}"
            if params:
                replacement += f" {params}"
            rendered_lines = [replacement]
            count("macro-definition")
        elif MACRO_END_RE.match(masked):
            rendered_lines = [f"{re.match(r'^\s*', code).group()}.endm"]
            active_macro = None
            count("macro-end")
        else:
            if SCOPE_RE.match(masked):
                scope += 1
            rewritten, implicit_label = rewrite_implicit_label(code, macros)
            if implicit_label:
                count("implicit-label")
            rewritten, invoked = rewrite_macro_invocation(rewritten, macros)
            if invoked:
                count("macro-invocation")
            before_locals = rewritten
            rewritten = rewrite_locals(rewritten, analysis, scope, active_macro, line_number)
            if rewritten != before_locals:
                count("local-label")
            rewritten, directive = rewrite_directive(rewritten, analysis, line_number)
            if directive:
                count(directive)
            rewritten = rewrite_literals_and_locations(rewritten)
            if active_macro is not None:
                rewritten = replace_macro_params(rewritten, active_macro)
            rewritten, alu_parentheses = rewrite_alu_parentheses(rewritten)
            if alu_parentheses:
                count("alu-parentheses")
            rendered_lines, wide_copy = split_wide_register_copy(rewritten)
            if wide_copy:
                count("wide-register-copy")

        for output_index, rendered in enumerate(rendered_lines):
            suffix = comment if output_index == len(rendered_lines) - 1 else ""
            remaining = mask_quoted(rendered)
            if "$" in remaining:
                raise FrontendError(
                    location.source,
                    location.line,
                    "unsupported-dollar",
                    f"unsupported or ambiguous '$' construct remains after translation: {remaining.strip()!r}",
                )
            output.append(f"{rendered}{suffix}\n")
            output_to_source.append(location.line)
            output_locations.append(location)

    return Translation(
        text="".join(output),
        analysis=analysis,
        output_to_source=output_to_source,
        output_locations=output_locations,
        transformations=dict(sorted(transformations.items())),
    )


def source_records(source_root: Path) -> list[tuple[str, Path, str]]:
    records: list[tuple[str, Path, str]] = []
    for top in ("src", "src_startup"):
        directory = source_root / top
        if not directory.is_dir():
            raise ValueError(f"missing assembly source directory: {directory}")
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"assembly source must not be a symlink: {path}")
            if path.is_file() and path.suffix.casefold() in ASSEMBLY_SUFFIXES:
                relative = path.relative_to(source_root).as_posix()
                records.append((relative, path, path.read_text(encoding="utf-8")))
    return records


def _metadata_relative_path(value: object, description: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{description} must be a non-empty POSIX relative path")
    if any(ord(character) < 32 or character == ":" for character in value):
        raise ValueError(f"{description} contains an unsafe character: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{description} is not a normalized relative path: {value!r}")
    if value == PREPARATION_METADATA:
        raise ValueError(f"{description} uses reserved path: {value}")
    return value


def _exact_object_keys(
    value: object,
    expected: set[str],
    description: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be an object")
    actual = set(value)
    if actual != expected:
        missing = ", ".join(sorted(expected - actual)) or "none"
        extra = ", ".join(sorted(actual - expected)) or "none"
        raise ValueError(
            f"{description} has wrong fields (missing: {missing}; extra: {extra})"
        )
    return value


def load_prepared_provenance(source_root: Path) -> PreparedProvenance:
    """Validate the preparation sidecar against every file in its input tree."""

    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError(f"prepared source root must be a real directory: {source_root}")
    source_root = source_root.resolve(strict=True)
    metadata_path = source_root / PREPARATION_METADATA
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise ValueError(
            f"prepared source metadata is missing or not a regular file: {metadata_path}"
        )
    try:
        metadata_bytes = metadata_path.read_bytes()
        document = json.loads(metadata_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"cannot read prepared source metadata {metadata_path}: {error}"
        ) from error

    root = _exact_object_keys(
        document,
        {"schema", "source", "files"},
        "prepared source metadata",
    )
    if root["schema"] != PREPARATION_SCHEMA or isinstance(root["schema"], bool):
        raise ValueError(
            f"prepared source metadata schema must be {PREPARATION_SCHEMA}"
        )
    source = _exact_object_keys(
        root["source"],
        {"head", "tracked_dirty"},
        "prepared source identity",
    )
    head = source["head"]
    if not isinstance(head, str) or GIT_OBJECT_RE.fullmatch(head) is None:
        raise ValueError("prepared source HEAD must be a full lowercase Git object ID")
    tracked_dirty = source["tracked_dirty"]
    if not isinstance(tracked_dirty, bool):
        raise ValueError("prepared source tracked_dirty must be a boolean")

    raw_files = root["files"]
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("prepared source metadata files must be a non-empty list")
    expected_files: dict[str, tuple[str, str]] = {}
    ordered_names: list[str] = []
    for ordinal, raw_entry in enumerate(raw_files):
        entry = _exact_object_keys(
            raw_entry,
            {"path", "sha256", "executable_bits"},
            f"prepared source file entry {ordinal}",
        )
        name = _metadata_relative_path(
            entry["path"], f"prepared source file entry {ordinal} path"
        )
        if name in expected_files:
            raise ValueError(f"duplicate prepared source file entry: {name}")
        digest = entry["sha256"]
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"invalid prepared source SHA-256 for {name}")
        executable_bits = entry["executable_bits"]
        if not isinstance(executable_bits, str) or re.fullmatch(
            r"[01]{3}", executable_bits
        ) is None:
            raise ValueError(f"invalid prepared source executable bits for {name}")
        ordered_names.append(name)
        expected_files[name] = (digest, executable_bits)
    if ordered_names != sorted(ordered_names):
        raise ValueError("prepared source file entries are not sorted by path")

    actual_files: dict[str, Path] = {}
    for path in sorted(source_root.rglob("*")):
        relative = path.relative_to(source_root).as_posix()
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"prepared source tree contains a symbolic link: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"prepared source tree contains a non-regular file: {relative}")
        if relative != PREPARATION_METADATA:
            actual_files[relative] = path

    expected_names = set(expected_files)
    actual_names = set(actual_files)
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    if missing:
        raise ValueError("prepared source tree is missing files: " + ", ".join(missing))
    if extra:
        raise ValueError("prepared source tree contains extra files: " + ", ".join(extra))

    for name in ordered_names:
        path = actual_files[name]
        expected_digest, expected_bits = expected_files[name]
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            raise ValueError(
                f"prepared source content is stale or modified: {name} "
                f"(expected {expected_digest}, found {actual_digest})"
            )
        actual_bits = f"{stat.S_IMODE(path.stat().st_mode) & 0o111:03o}"
        if actual_bits != expected_bits:
            raise ValueError(
                f"prepared source executable bits are stale or modified: {name} "
                f"(expected {expected_bits}, found {actual_bits})"
            )

    return PreparedProvenance(
        source_head=head,
        tracked_dirty=tracked_dirty,
        metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(),
        prepared_file_count=len(ordered_names),
    )


def resolve_include(
    source_root: Path,
    including: Path,
    spelling: str,
    external_include_roots: Sequence[Path],
) -> tuple[Path, str]:
    def resolve_case_compatibly(candidate: Path) -> Path | None:
        """Resolve one path as ZDS-on-Windows would, rejecting ambiguity."""

        if not candidate.is_absolute():
            raise ValueError(f"internal error: include candidate is not absolute: {candidate}")
        current = Path(candidate.anchor)
        for part in candidate.parts[1:]:
            if part in {"", "."}:
                continue
            if part == "..":
                current = current.parent
                continue
            exact = current / part
            try:
                exact.lstat()
            except FileNotFoundError:
                try:
                    matches = [
                        child
                        for child in current.iterdir()
                        if child.name.casefold() == part.casefold()
                    ]
                except (FileNotFoundError, NotADirectoryError, PermissionError):
                    return None
                if not matches:
                    return None
                if len(matches) != 1:
                    spellings = ", ".join(sorted(child.name for child in matches))
                    raise ValueError(
                        f"ambiguous case-insensitive include component {part!r} "
                        f"under {current}: {spellings}"
                    )
                current = matches[0]
            else:
                current = exact
        return current

    relative_spelling = spelling.replace("\\", "/")
    requested = PurePosixPath(relative_spelling)
    if requested.is_absolute():
        raise ValueError(f"unsafe include path {spelling!r} in {including}")
    source_root = source_root.resolve(strict=True)
    resolved_external_roots = tuple(root.resolve(strict=True) for root in external_include_roots)
    candidates = [including.parent / Path(relative_spelling)]
    candidates.extend(root / Path(relative_spelling) for root in resolved_external_roots)
    allowed_roots = (source_root, *resolved_external_roots)
    for candidate in candidates:
        matched = resolve_case_compatibly(candidate)
        if matched is None or matched.is_symlink():
            continue
        try:
            resolved = matched.resolve(strict=True)
        except FileNotFoundError:
            continue
        if not resolved.is_file():
            continue
        if not any(resolved == root or root in resolved.parents for root in allowed_roots):
            continue
        try:
            display = resolved.relative_to(source_root).as_posix()
        except ValueError:
            display = f"toolchain/{resolved.name}"
        return resolved, display
    raise ValueError(f"unresolved include {spelling!r} at {including}")


def expand_translation_unit(
    source_root: Path,
    entry_relative: str,
    external_include_roots: Sequence[Path] = (),
    external_include_aliases: dict[str, Path] | None = None,
) -> ExpandedSource:
    """Textually expand ZDS INCLUDEs; an included END returns to its caller."""

    source_root = source_root.resolve(strict=True)
    entry = (source_root / entry_relative).resolve(strict=True)
    includes: list[dict[str, object]] = []
    source_files: dict[str, str] = {}
    output: list[str] = []
    locations: list[SourceLocation] = []

    def visit(path: Path, display: str, stack: tuple[Path, ...], is_root: bool) -> None:
        if path in stack:
            chain = " -> ".join(item.as_posix() for item in (*stack, path))
            raise ValueError(f"recursive include chain: {chain}")
        text = path.read_text(encoding="utf-8")
        source_files[display] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        physical_lines = text.splitlines(keepends=True)
        for line_number, physical in enumerate(physical_lines, 1):
            line, _ = split_physical_line(physical)
            code, _ = split_comment(line)
            masked = mask_quoted(code)
            include = INCLUDE_RE.match(code)
            if include:
                spelling = include.group("path")[1:-1]
                alias = (external_include_aliases or {}).get(spelling.casefold())
                if alias is not None:
                    target = alias.resolve(strict=True)
                    target_display = f"toolchain/{target.name}"
                else:
                    target, target_display = resolve_include(
                        source_root, path, spelling, external_include_roots
                    )
                includes.append(
                    {
                        "from": display,
                        "line": line_number,
                        "spelling": spelling,
                        "resolved": target_display,
                    }
                )
                visit(target, target_display, (*stack, path), False)
                continue
            if END_RE.match(masked):
                if is_root:
                    output.append(physical if physical.endswith(("\n", "\r")) else physical + "\n")
                    locations.append(SourceLocation(display, line_number))
                break
            # Includes are expanded before analysis and translation, so this
            # marker cannot be mistaken for a live assembler include if a
            # location-map bug is ever introduced.
            output.append(physical if physical.endswith(("\n", "\r")) else physical + "\n")
            locations.append(SourceLocation(display, line_number))

    visit(entry, entry_relative, (), True)
    return ExpandedSource(
        "".join(output),
        tuple(locations),
        tuple(includes),
        tuple(
            {"source": source, "sha256": digest}
            for source, digest in sorted(source_files.items())
        ),
    )


def manifest_entry(
    relative: str,
    source_text: str,
    translation: Translation,
    includes: Sequence[dict[str, object]] = (),
    source_files: Sequence[dict[str, str]] = (),
) -> dict[str, object]:
    return {
        "source": relative,
        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "output": relative,
        "output_sha256": hashlib.sha256(translation.text.encode("utf-8")).hexdigest(),
        "input_lines": len(source_text.splitlines()),
        "output_lines": len(translation.output_to_source),
        "output_to_source": translation.output_to_source,
        "output_locations": [dataclasses.asdict(item) for item in translation.output_locations],
        "includes": list(includes),
        "source_files": list(source_files),
        "scopes": translation.analysis.scopes,
        "mappings": translation.analysis.mappings,
        "sections": list(translation.analysis.section_definitions.values()),
        "structures": [
            {
                "name": structure.name,
                "size_name": structure.size_name,
                "size": structure.size,
                "defined_at": f"{structure.source}:{structure.line}",
                "members": [dataclasses.asdict(member) for member in structure.members],
            }
            for structure in translation.analysis.structures.values()
        ],
        "transformations": translation.transformations,
    }


def atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(data, encoding="utf-8", newline="")
    os.replace(temporary, path)


def validate_output_root(source_root: Path, output_root: Path) -> None:
    source = source_root.resolve(strict=True)
    output = output_root.resolve(strict=False)
    if output == source or source in output.parents:
        raise ValueError("output root must not be the source root or a child of it")
    if output_root.is_symlink():
        raise ValueError(f"output root must not be a symlink: {output_root}")


def translate_tree(source_root: Path, output_root: Path, check: bool) -> dict[str, object]:
    validate_output_root(source_root, output_root)
    provenance = load_prepared_provenance(source_root)
    records = source_records(source_root)
    macro_table = discover_macros([(relative, text) for relative, _, text in records])
    translated: list[
        tuple[
            str,
            str,
            Translation,
            tuple[dict[str, object], ...],
            tuple[dict[str, str], ...],
        ]
    ] = []
    assembly_roots = [
        relative for relative, path, _ in records if path.suffix.casefold() == ".asm"
    ]
    external_roots = (Path(__file__).resolve().parents[3] / "toolchains" / "agondev" / "include",)
    external_aliases = {"ez80f92.inc": external_roots[0] / "ez80f92.inc"}
    for relative in assembly_roots:
        source_text = (source_root / relative).read_text(encoding="utf-8")
        expanded = expand_translation_unit(
            source_root, relative, external_roots, external_aliases
        )
        root_macros = discover_macros([(relative, expanded.text)])
        translated.append(
            (
                relative,
                source_text,
                translate(
                    relative,
                    expanded.text,
                    root_macros,
                    expanded.locations,
                    provenance.identity,
                ),
                expanded.includes,
                expanded.source_files,
            )
        )

    manifest: dict[str, object] = {
        "schema": FRONTEND_VERSION,
        "input_identity": provenance.identity,
        "input_provenance": {
            "metadata": PREPARATION_METADATA,
            "metadata_sha256": provenance.metadata_sha256,
            "prepared_file_count": provenance.prepared_file_count,
            "source_head": provenance.source_head,
            "tracked_dirty": provenance.tracked_dirty,
        },
        "anonymous_label_strategy": ANONYMOUS_LABEL_STRATEGY,
        "files": [
            manifest_entry(relative, source, result, includes, source_files)
            for relative, source, result, includes, source_files in translated
        ],
        "macros": [
            {
                "source": macro.source_name,
                "generated": macro.gas_name,
                "parameters": list(macro.params),
                "defined_at": f"{macro.source}:{macro.line}",
            }
            for macro in sorted(macro_table.values(), key=lambda item: item.source_name)
        ],
    }
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    if check:
        for relative, _, result, _, _ in translated:
            target = output_root / relative
            if not target.is_file() or target.read_text(encoding="utf-8") != result.text:
                raise ValueError(f"generated output is missing or stale: {target}")
        manifest_path = output_root / "manifest.json"
        if not manifest_path.is_file() or manifest_path.read_text(encoding="utf-8") != manifest_text:
            raise ValueError(f"generated manifest is missing or stale: {manifest_path}")
    else:
        if output_root.exists() and not output_root.is_dir():
            raise ValueError(f"output root is not a directory: {output_root}")
        output_root.mkdir(parents=True, exist_ok=True)
        for relative, _, result, _, _ in translated:
            atomic_write(output_root / relative, result.text)
        atomic_write(output_root / "manifest.json", manifest_text)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    tree = subparsers.add_parser("tree", help="translate the MOS src and src_startup trees")
    tree.add_argument("source_root", type=Path)
    tree.add_argument("output_root", type=Path)
    tree.add_argument("--check", action="store_true", help="fail unless existing output is current")

    provenance = subparsers.add_parser(
        "provenance", help="validate a prepared MOS tree and its source metadata"
    )
    provenance.add_argument("source_root", type=Path)

    one_file = subparsers.add_parser("file", help="translate one self-contained assembly file")
    one_file.add_argument("input", type=Path)
    one_file.add_argument("output", type=Path)
    one_file.add_argument("--source-name", help="stable name used for local-label mangling")
    one_file.add_argument("--manifest", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "provenance":
            provenance = load_prepared_provenance(args.source_root)
            print(
                "zds2gas: prepared source verified: "
                f"{provenance.prepared_file_count} files, {provenance.identity}"
            )
            return 0

        if args.command == "tree":
            manifest = translate_tree(args.source_root, args.output_root, args.check)
            print(f"zds2gas: {len(manifest['files'])} files, {len(manifest['macros'])} macros")
            return 0

        source_name = args.source_name or args.input.name
        source_text = args.input.read_text(encoding="utf-8")
        result = translate(source_name, source_text)
        atomic_write(args.output, result.text)
        if args.manifest:
            manifest = {
                "schema": FRONTEND_VERSION,
                "anonymous_label_strategy": ANONYMOUS_LABEL_STRATEGY,
                "files": [manifest_entry(source_name, source_text, result)],
            }
            atomic_write(args.manifest, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return 0
    except (FrontendError, OSError, UnicodeError, ValueError) as error:
        print(f"zds2gas: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
