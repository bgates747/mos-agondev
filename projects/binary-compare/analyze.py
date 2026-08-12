#!/usr/bin/env python3
"""Classify an AgonDev MOS image against the pinned official ZDS release."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parents[1]
DEFAULT_REFERENCE_MANIFEST = PROJECT / "reference" / "v3.0.2.json"
DEFAULT_REFERENCE = PROJECT / "artifacts" / "reference" / "v3.0.2"
DEFAULT_CANDIDATE = PROJECT / "artifacts" / "candidate"
DEFAULT_OUTPUT = PROJECT / "artifacts" / "report"
DEFAULT_TOOLCHAIN = ROOT / "toolchains" / "agondev"
DEFAULT_SOURCE_REPO = ROOT / "upstream" / "agon-mos"


EXECUTABLE_SEGMENTS = {".RESET", ".IVECTS", ".STARTUP", "CODE"}
SEGMENT_TO_GNU = {
    ".RESET": ".RESET",
    ".IVECTS": ".IVECTS",
    ".STARTUP": ".STARTUP",
    "CODE": ".text",
    "TEXT": ".rodata",
    "STRSECT": ".rodata",
    "DATA": ".data",
    "BSS": ".bss",
    "IVJMPTBL": ".bss",
}


class AnalysisError(RuntimeError):
    pass


def sanitize_zds_option(option: str) -> str:
    if option.startswith("-stdinc:"):
        return "-stdinc:<ZDS-standard-includes>"
    if option.startswith("-usrinc:"):
        return "-usrinc:<release-project-includes>"
    if option.startswith("-include:"):
        return "-include:<ZDS-standard-includes>"
    return option


@dataclass(frozen=True)
class ModuleRange:
    module: str
    object_name: str
    source_kind: str
    segment: str
    address_space: str
    address: int
    size: int

    @property
    def end(self) -> int:
        return self.address + self.size

    @property
    def stem(self) -> str:
        name = PurePosixPath(self.object_name.replace("\\", "/")).name
        return name.rsplit(".", 1)[0].lower()


@dataclass(frozen=True)
class Symbol:
    name: str
    address: int
    address_space: str
    module: str
    segment: str
    symbol_type: str = ""
    size: int = 0


@dataclass(frozen=True)
class CandidateRange:
    section: str
    address: int
    size: int
    object_path: str

    @property
    def end(self) -> int:
        return self.address + self.size

    @property
    def stem(self) -> str:
        value = self.object_path
        if ".a(" in value:
            value = value.rsplit("(", 1)[1].rstrip(")")
        return PurePosixPath(value).name.rsplit(".", 1)[0].lower()


@dataclass(frozen=True)
class Instruction:
    address: int
    raw: bytes
    text: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular(path: Path, description: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise AnalysisError(f"{description} is not a regular file: {path}")


def load_json(path: Path) -> dict[str, Any]:
    require_regular(path, "JSON input")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AnalysisError(f"expected a JSON object in {path}")
    return value


def parse_zds_map(text: str) -> tuple[list[ModuleRange], list[Symbol], dict[str, Any]]:
    modules: list[ModuleRange] = []
    symbols: list[Symbol] = []
    metadata: dict[str, Any] = {
        "compiler_options": [],
        "assembler_options": [],
        "linker_options": [],
    }
    current: tuple[str, str, str] | None = None
    in_external_definitions = False
    module_re = re.compile(r"^Module:\s+(.+?)\s+\((File|Library):\s*([^)]+)\)")
    segment_re = re.compile(
        r"^\s+Segment:\s+(\S+)\s+([CD]):([0-9A-F]+)\s+"
        r"[CD]:([0-9A-F]+)\s+([0-9A-F]+)h\s*$",
        re.IGNORECASE,
    )
    symbol_re = re.compile(
        r"^(\S+)\s+([CD]):([0-9A-F]+)\s+(\S+)\s+(\S+)\s*$",
        re.IGNORECASE,
    )
    absolute_symbol_re = re.compile(
        r"^(\S+)\s+([0-9A-F]{8})\s+\(User Defined\)\s*$",
        re.IGNORECASE,
    )
    option_section: str | None = None
    for raw_line in text.replace("\r", "").splitlines():
        line = raw_line.strip("\f")
        if line.startswith("IEEE 695 OMF Linker Version"):
            metadata["linker"] = line.strip()
        elif line.startswith("DATE:"):
            metadata["date"] = line.split(":", 1)[1].strip()
        elif line.startswith("PROCESSOR:"):
            metadata["processor"] = line.split(":", 1)[1].strip()
        elif "ZDS II - eZ80Acclaim!" in line:
            metadata["zds"] = line.strip().strip("/* ")

        stripped = line.strip()
        if stripped == "/* compiler options */":
            option_section = "compiler_options"
            continue
        if stripped == "/* assembler options */":
            option_section = "assembler_options"
            continue
        if stripped.startswith("-FORMAT="):
            option_section = None
        if option_section is not None and stripped.startswith("/*"):
            option = stripped.removeprefix("/*").removesuffix("*/").strip()
            if option and not option.startswith(("compiler options", "assembler options")):
                metadata[option_section].append(sanitize_zds_option(option))
        if stripped.startswith(("-FORMAT=", "-map ", "-sort ")):
            metadata["linker_options"].append(stripped)

        module_match = module_re.match(line)
        if module_match:
            current = (
                module_match.group(1).strip(),
                module_match.group(3).strip(),
                module_match.group(2).lower(),
            )
            continue
        segment_match = segment_re.match(line)
        if segment_match and current is not None:
            segment, address_space, base_hex, top_hex, size_hex = segment_match.groups()
            base = int(base_hex, 16)
            top = int(top_hex, 16)
            size = int(size_hex, 16)
            if top - base + 1 != size:
                raise AnalysisError(
                    f"inconsistent ZDS module range for {current[1]} {segment}"
                )
            modules.append(
                ModuleRange(
                    module=current[0],
                    object_name=current[1],
                    source_kind=current[2],
                    segment=segment,
                    address_space=address_space.upper(),
                    address=base,
                    size=size,
                )
            )
            continue
        if line.strip() == "EXTERNAL DEFINITIONS:":
            in_external_definitions = True
            current = None
            continue
        if line.strip() == "SYMBOL CROSS REFERENCE:":
            in_external_definitions = False
            continue
        if in_external_definitions:
            symbol_match = symbol_re.match(line)
            if symbol_match:
                name, address_space, address_hex, module, segment = symbol_match.groups()
                symbols.append(
                    Symbol(
                        name=name,
                        address=int(address_hex, 16),
                        address_space=address_space.upper(),
                        module=module,
                        segment=segment,
                    )
                )
                continue
            absolute_match = absolute_symbol_re.match(line)
            if absolute_match:
                name, address_hex = absolute_match.groups()
                symbols.append(
                    Symbol(
                        name=name,
                        address=int(address_hex, 16),
                        address_space="A",
                        module="LINKER",
                        segment="ABS",
                    )
                )
    if not modules or not symbols:
        raise AnalysisError("ZDS map parser found no modules or external symbols")
    return modules, symbols, metadata


def parse_gnu_map(text: str) -> list[CandidateRange]:
    ranges: list[CandidateRange] = []
    row_re = re.compile(
        r"^\s+(\.[A-Za-z0-9_.$]+)\s+0x([0-9A-Fa-f]+)\s+"
        r"0x([0-9A-Fa-f]+)\s+(\S.*)$"
    )
    for line in text.splitlines():
        match = row_re.match(line)
        if not match:
            continue
        section, address_hex, size_hex, object_path = match.groups()
        object_path = object_path.strip()
        if ".o" not in object_path and ".a(" not in object_path:
            continue
        ranges.append(
            CandidateRange(
                section=section,
                address=int(address_hex, 16),
                size=int(size_hex, 16),
                object_path=object_path,
            )
        )
    if not ranges:
        raise AnalysisError("GNU map parser found no input-section ranges")
    return ranges


def parse_nm(text: str) -> list[Symbol]:
    symbols: list[Symbol] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 3:
            address_hex, symbol_type, name = fields
            size = 0
        elif len(fields) == 4:
            address_hex, size_hex, symbol_type, name = fields
            if not re.fullmatch(r"[0-9A-Fa-f]+", size_hex):
                continue
            size = int(size_hex, 16)
        else:
            continue
        if not re.fullmatch(r"[0-9A-Fa-f]+", address_hex):
            continue
        symbols.append(
            Symbol(
                name=name,
                address=int(address_hex, 16),
                address_space="D" if symbol_type.lower() in {"b", "d"} else "C",
                module="",
                segment="",
                symbol_type=symbol_type,
                size=size,
            )
        )
    if not symbols:
        raise AnalysisError("candidate nm parser found no symbols")
    return symbols


def candidate_range_for(
    reference_range: ModuleRange,
    candidate_ranges: list[CandidateRange],
    reference_ranges: list[ModuleRange],
) -> CandidateRange | None:
    expected_section = SEGMENT_TO_GNU.get(reference_range.segment)
    if expected_section is None:
        return None
    matches = [
        item
        for item in candidate_ranges
        if item.stem == reference_range.stem and item.section == expected_section
    ]
    nonempty = [item for item in matches if item.size]
    choices = nonempty or matches
    # ZDS places assembly constants declared in SEGMENT TEXT in a distinct
    # ROM range. GAS retains those bytes in the assembly object's .text. Split
    # that one candidate input range deterministically when its size is the
    # exact sum of the ZDS CODE and TEXT ranges for the module.
    if reference_range.module.lower().endswith(".asm") and reference_range.segment in {
        "CODE",
        "TEXT",
    }:
        text_matches = [
            item
            for item in candidate_ranges
            if item.stem == reference_range.stem and item.section == ".text" and item.size
        ]
        module_parts = [
            item
            for item in reference_ranges
            if item.stem == reference_range.stem and item.segment in {"CODE", "TEXT"}
        ]
        if len(text_matches) == 1 and {item.segment for item in module_parts} == {"CODE", "TEXT"}:
            candidate = text_matches[0]
            code = next(item for item in module_parts if item.segment == "CODE")
            text = next(item for item in module_parts if item.segment == "TEXT")
            if candidate.size == code.size + text.size:
                offset = 0 if reference_range.segment == "CODE" else code.size
                return CandidateRange(
                    section=candidate.section,
                    address=candidate.address + offset,
                    size=reference_range.size,
                    object_path=candidate.object_path,
                )
    if len(choices) == 1:
        return choices[0]
    return None


def shared_symbol_tokens(
    reference_symbols: list[Symbol], candidate_symbols: list[Symbol]
) -> tuple[dict[int, str], dict[int, str], dict[str, tuple[int, int]]]:
    reference_by_name = {item.name: item for item in reference_symbols}
    candidate_by_name = {item.name: item for item in candidate_symbols}
    shared: dict[str, tuple[int, int]] = {}
    pairs: dict[tuple[int, int], list[str]] = collections.defaultdict(list)
    for name in sorted(reference_by_name.keys() & candidate_by_name.keys()):
        reference = reference_by_name[name]
        candidate = candidate_by_name[name]
        shared[name] = (reference.address, candidate.address)
        pairs[(reference.address, candidate.address)].append(name)

    def preference(name: str) -> tuple[int, int, str]:
        return (len(name) - len(name.lstrip("_")), len(name), name)

    reference_tokens: dict[int, str] = {}
    candidate_tokens: dict[int, str] = {}
    ambiguous_reference: set[int] = set()
    ambiguous_candidate: set[int] = set()
    for (reference_address, candidate_address), names in pairs.items():
        token = "@" + min(names, key=preference)
        if reference_address in reference_tokens and reference_tokens[reference_address] != token:
            ambiguous_reference.add(reference_address)
        else:
            reference_tokens[reference_address] = token
        if candidate_address in candidate_tokens and candidate_tokens[candidate_address] != token:
            ambiguous_candidate.add(candidate_address)
        else:
            candidate_tokens[candidate_address] = token
    for address in ambiguous_reference:
        reference_tokens.pop(address, None)
    for address in ambiguous_candidate:
        candidate_tokens.pop(address, None)
    return reference_tokens, candidate_tokens, shared


def run_disassembler(
    objdump: Path, binary: Path, start: int, end: int
) -> list[Instruction]:
    if end <= start:
        return []
    result = subprocess.run(
        [
            str(objdump),
            "-D",
            "-b",
            "binary",
            "-m",
            "ez80-adl",
            "-z",
            f"--start-address=0x{start:x}",
            f"--stop-address=0x{end:x}",
            str(binary),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise AnalysisError(
            f"objdump failed for {binary.name} 0x{start:x}:0x{end:x}: "
            f"{result.stderr.strip()}"
        )
    row_re = re.compile(
        r"^\s*([0-9A-Fa-f]+):\s+((?:[0-9A-Fa-f]{2}(?:\s+|$))+?)\s{2,}(.+?)\s*$"
    )
    instructions: list[Instruction] = []
    for line in result.stdout.splitlines():
        match = row_re.match(line)
        if not match:
            continue
        address_hex, raw_hex, text = match.groups()
        raw = bytes.fromhex(" ".join(raw_hex.split()))
        instructions.append(Instruction(int(address_hex, 16), raw, text.strip()))
    if not instructions:
        raise AnalysisError(f"objdump produced no instructions for 0x{start:x}:0x{end:x}")
    cursor = start
    for instruction in instructions:
        if instruction.address != cursor:
            raise AnalysisError(
                f"non-contiguous disassembly at 0x{cursor:x}: got 0x{instruction.address:x}"
            )
        cursor += len(instruction.raw)
    if cursor != end:
        raise AnalysisError(
            f"disassembly did not cover requested range 0x{start:x}:0x{end:x}; "
            f"stopped at 0x{cursor:x}"
        )
    return instructions


def raw_disassembly_text(objdump: Path, binary: Path) -> str:
    result = subprocess.run(
        [str(objdump), "-D", "-b", "binary", "-m", "ez80-adl", "-z", str(binary)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise AnalysisError(f"whole-image objdump failed: {result.stderr.strip()}")
    return result.stdout.replace(str(binary), "MOS.bin")


def normalize_instructions(
    instructions: Iterable[Instruction],
    address_tokens: dict[int, str],
    context_start: int,
    context_end: int,
) -> tuple[list[str], int]:
    replacements = 0

    def replace_hex(match: re.Match[str]) -> str:
        nonlocal replacements
        value = int(match.group(1), 16)
        token = address_tokens.get(value) if value >= 0x100 else None
        if token is not None:
            replacements += 1
            return token
        if context_start <= value < context_end:
            replacements += 1
            return f"@self+0x{value - context_start:x}"
        return match.group(0).lower()

    normalized = []
    for instruction in instructions:
        text = " ".join(instruction.text.lower().split())
        text = re.sub(r"0x([0-9a-f]+)", replace_hex, text)
        normalized.append(text)
    return normalized, replacements


def paired_value_token(
    reference_value: int,
    candidate_value: int,
    paired_tokens: dict[tuple[int, int], str],
    reference_context: tuple[int, int],
    candidate_context: tuple[int, int],
) -> str | None:
    direct = paired_tokens.get((reference_value, candidate_value))
    if direct is not None:
        return direct
    best: tuple[int, str] | None = None
    for (reference_base, candidate_base), token in paired_tokens.items():
        reference_offset = reference_value - reference_base
        candidate_offset = candidate_value - candidate_base
        if (
            0 <= reference_offset <= 0x100
            and reference_offset == candidate_offset
            and (best is None or reference_offset < best[0])
        ):
            rendered = token if reference_offset == 0 else f"{token}+0x{reference_offset:x}"
            best = (reference_offset, rendered)
    if best is not None:
        return best[1]
    reference_offset = reference_value - reference_context[0]
    candidate_offset = candidate_value - candidate_context[0]
    if (
        reference_context[0] <= reference_value < reference_context[1]
        and candidate_context[0] <= candidate_value < candidate_context[1]
        and reference_offset == candidate_offset
    ):
        return f"@self+0x{reference_offset:x}"
    return None


def relocation_byte_spans(
    reference: bytes,
    candidate: bytes,
    reference_context: tuple[int, int],
    candidate_context: tuple[int, int],
    paired_tokens: dict[tuple[int, int], str],
) -> list[dict[str, Any]] | None:
    """Cover byte differences only with recognized little-endian addresses."""

    if len(reference) != len(candidate):
        return None
    mismatches = {index for index, pair in enumerate(zip(reference, candidate)) if pair[0] != pair[1]}
    if not mismatches:
        return []
    candidates: list[tuple[int, int, int, int, str]] = []
    for width in (3, 2, 4):
        for start in range(max(0, len(reference) - width + 1)):
            reference_value = int.from_bytes(reference[start : start + width], "little")
            candidate_value = int.from_bytes(candidate[start : start + width], "little")
            if reference_value == candidate_value or reference_value > 0xFFFFFF or candidate_value > 0xFFFFFF:
                continue
            token = paired_value_token(
                reference_value,
                candidate_value,
                paired_tokens,
                reference_context,
                candidate_context,
            )
            if token is not None:
                candidates.append((start, width, reference_value, candidate_value, token))
    covered: set[int] = set()
    selected: list[dict[str, Any]] = []
    for start, width, reference_value, candidate_value, token in candidates:
        span = set(range(start, start + width))
        newly_covered = (span & mismatches) - covered
        if not newly_covered:
            continue
        covered.update(span & mismatches)
        selected.append(
            {
                "offset": start,
                "width": width,
                "reference_value": reference_value,
                "candidate_value": candidate_value,
                "token": token,
            }
        )
    return selected if covered == mismatches else None


def normalize_paired_local_targets(
    reference: list[Instruction],
    candidate: list[Instruction],
    reference_context: tuple[int, int],
    candidate_context: tuple[int, int],
    reference_tokens: dict[int, str],
    candidate_tokens: dict[int, str],
    paired_tokens: dict[tuple[int, int], str],
) -> tuple[list[str], list[str], int]:
    """Normalize corresponding relocated targets within paired module ranges.

    A numeric operand is treated as module-relative only when the two
    instruction spellings have identical nonnumeric structure, the values
    differ, and both values have the same offset in their respective module.
    Identical numeric constants are deliberately left untouched.
    """

    if len(reference) != len(candidate):
        return [], [], 0
    numeric = re.compile(r"0x([0-9a-f]+)", re.IGNORECASE)
    ordered_reference_tokens = sorted(reference_tokens)
    ordered_candidate_tokens = sorted(candidate_tokens)

    def symbol_relative(
        value: int, tokens: dict[int, str], ordered: list[int]
    ) -> str | None:
        if value < 0x100:
            return None
        for base in reversed(ordered):
            if base > value:
                continue
            offset = value - base
            if offset > 0x100:
                return None
            token = tokens[base]
            return token if offset == 0 else f"{token}+0x{offset:x}"
        return None

    reference_output: list[str] = []
    candidate_output: list[str] = []
    replacements = 0
    for reference_instruction, candidate_instruction in zip(reference, candidate):
        reference_text = " ".join(reference_instruction.text.lower().split())
        candidate_text = " ".join(candidate_instruction.text.lower().split())
        reference_values = [int(value, 16) for value in numeric.findall(reference_text)]
        candidate_values = [int(value, 16) for value in numeric.findall(candidate_text)]
        reference_shape = numeric.sub("{}", reference_text)
        candidate_shape = numeric.sub("{}", candidate_text)
        if reference_shape != candidate_shape or len(reference_values) != len(candidate_values):
            reference_output.append(reference_text)
            candidate_output.append(candidate_text)
            continue
        reference_parts: list[str] = []
        candidate_parts: list[str] = []
        cursor_reference = 0
        cursor_candidate = 0
        for reference_match, candidate_match, reference_value, candidate_value in zip(
            numeric.finditer(reference_text),
            numeric.finditer(candidate_text),
            reference_values,
            candidate_values,
        ):
            reference_parts.append(reference_text[cursor_reference : reference_match.start()])
            candidate_parts.append(candidate_text[cursor_candidate : candidate_match.start()])
            if reference_value == candidate_value:
                token = f"0x{reference_value:x}"
                reference_parts.append(token)
                candidate_parts.append(token)
            else:
                direct_token = paired_tokens.get((reference_value, candidate_value))
                relative_pair_token = paired_value_token(
                    reference_value,
                    candidate_value,
                    paired_tokens,
                    reference_context,
                    candidate_context,
                )
                reference_offset = reference_value - reference_context[0]
                candidate_offset = candidate_value - candidate_context[0]
                reference_symbol = symbol_relative(
                    reference_value, reference_tokens, ordered_reference_tokens
                )
                candidate_symbol = symbol_relative(
                    candidate_value, candidate_tokens, ordered_candidate_tokens
                )
                if direct_token is not None or relative_pair_token is not None:
                    token = direct_token or relative_pair_token
                    assert token is not None
                    reference_parts.append(token)
                    candidate_parts.append(token)
                    replacements += 1
                elif reference_symbol is not None and reference_symbol == candidate_symbol:
                    reference_parts.append(reference_symbol)
                    candidate_parts.append(candidate_symbol)
                    replacements += 1
                elif (
                    reference_context[0] <= reference_value < reference_context[1]
                    and candidate_context[0] <= candidate_value < candidate_context[1]
                    and reference_offset == candidate_offset
                ):
                    token = f"@self+0x{reference_offset:x}"
                    reference_parts.append(token)
                    candidate_parts.append(token)
                    replacements += 1
                else:
                    reference_parts.append(f"0x{reference_value:x}")
                    candidate_parts.append(f"0x{candidate_value:x}")
            cursor_reference = reference_match.end()
            cursor_candidate = candidate_match.end()
        reference_parts.append(reference_text[cursor_reference:])
        candidate_parts.append(candidate_text[cursor_candidate:])
        reference_output.append("".join(reference_parts))
        candidate_output.append("".join(candidate_parts))
    return reference_output, candidate_output, replacements


def compare_executable_range(
    *,
    objdump: Path,
    reference_binary: Path,
    candidate_binary: Path,
    reference_start: int,
    reference_end: int,
    candidate_start: int,
    candidate_end: int,
    reference_tokens: dict[int, str],
    candidate_tokens: dict[int, str],
    paired_tokens: dict[tuple[int, int], str],
    reference_context: tuple[int, int] | None = None,
    candidate_context: tuple[int, int] | None = None,
) -> tuple[str, str, str, dict[str, Any]]:
    reference_data = reference_binary.read_bytes()[reference_start:reference_end]
    candidate_data = candidate_binary.read_bytes()[candidate_start:candidate_end]
    details = {
        "reference_size": len(reference_data),
        "candidate_size": len(candidate_data),
        "reference_replacements": 0,
        "candidate_replacements": 0,
    }
    if reference_data == candidate_data:
        return "exact", "high", "bytes-identical", details
    relocation_spans = relocation_byte_spans(
        reference_data,
        candidate_data,
        reference_context or (reference_start, reference_end),
        candidate_context or (candidate_start, candidate_end),
        paired_tokens,
    )
    if relocation_spans is not None:
        details["relocation_byte_spans"] = relocation_spans
        return (
            "relocation-only",
            "medium",
            "all-byte-differences-covered-by-recognized-d24-address-relocations",
            details,
        )
    reference_disassembly = run_disassembler(
        objdump, reference_binary, reference_start, reference_end
    )
    candidate_disassembly = run_disassembler(
        objdump, candidate_binary, candidate_start, candidate_end
    )
    reference_context = reference_context or (reference_start, reference_end)
    candidate_context = candidate_context or (candidate_start, candidate_end)
    reference_normalized, reference_count = normalize_instructions(
        reference_disassembly,
        reference_tokens,
        reference_context[0],
        reference_context[1],
    )
    candidate_normalized, candidate_count = normalize_instructions(
        candidate_disassembly,
        candidate_tokens,
        candidate_context[0],
        candidate_context[1],
    )
    details["reference_replacements"] = reference_count
    details["candidate_replacements"] = candidate_count
    if reference_normalized == candidate_normalized:
        if reference_count and candidate_count:
            return (
                "relocation-only",
                "medium",
                "instruction-stream-equal-after-shared-symbol-address-normalization",
                details,
            )
        return (
            "instruction-equivalent",
            "medium",
            "disassembly-text-identical-with-different-encoding-bytes",
            details,
        )
    paired_reference, paired_candidate, paired_count = normalize_paired_local_targets(
        reference_disassembly,
        candidate_disassembly,
        reference_context,
        candidate_context,
        reference_tokens,
        candidate_tokens,
        paired_tokens,
    )
    if paired_reference and paired_reference == paired_candidate and paired_count:
        details["paired_module_relative_replacements"] = paired_count
        return (
            "relocation-only",
            "medium",
            "instruction-stream-equal-after-paired-module-relative-normalization",
            details,
        )
    details["reference_instruction_count"] = len(reference_normalized)
    details["candidate_instruction_count"] = len(candidate_normalized)
    mismatch_reference = paired_reference or reference_normalized
    mismatch_candidate = paired_candidate or candidate_normalized
    mismatch = next(
        (
            index
            for index, pair in enumerate(zip(mismatch_reference, mismatch_candidate))
            if pair[0] != pair[1]
        ),
        min(len(mismatch_reference), len(mismatch_candidate)),
    )
    details["first_mismatch_instruction"] = mismatch
    if mismatch < len(mismatch_reference):
        details["reference_first_mismatch"] = mismatch_reference[mismatch]
    if mismatch < len(mismatch_candidate):
        details["candidate_first_mismatch"] = mismatch_candidate[mismatch]
    return "unexplained", "none", "normalized-instruction-stream-differs", details


def source_divergence(source_repo: Path, release_commit: str) -> list[dict[str, str]]:
    if source_repo.is_symlink():
        source_repo = source_repo.resolve()
    result = subprocess.run(
        ["git", "diff", "--name-status", release_commit],
        cwd=source_repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise AnalysisError(f"cannot compare candidate source with release: {result.stderr}")
    changes = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) >= 2:
            changes.append({"status": fields[0], "path": fields[-1]})
    return changes


def binary_difference_summary(reference: bytes, candidate: bytes) -> dict[str, int | None]:
    common = min(len(reference), len(candidate))
    mismatches = [index for index in range(common) if reference[index] != candidate[index]]
    prefix = 0
    while prefix < common and reference[prefix] == candidate[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < common - prefix
        and reference[len(reference) - 1 - suffix] == candidate[len(candidate) - 1 - suffix]
    ):
        suffix += 1
    return {
        "reference_size": len(reference),
        "candidate_size": len(candidate),
        "common_offset_bytes": common,
        "same_offset_equal_bytes": common - len(mismatches),
        "same_offset_different_bytes": len(mismatches),
        "first_same_offset_difference": mismatches[0] if mismatches else None,
        "last_same_offset_difference": mismatches[-1] if mismatches else None,
        "common_prefix_bytes": prefix,
        "common_suffix_bytes": suffix,
    }


def stable_comparison_digest(items: list[dict[str, Any]]) -> str:
    selected = [
        {
            "id": item["id"],
            "classification": item["classification"],
            "reason": item["reason"],
            "reference": item["reference"],
            "candidate": item["candidate"],
        }
        for item in sorted(items, key=lambda item: item["id"])
    ]
    encoded = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def symbol_order_comparisons(
    reference_symbols: list[Symbol], candidate_symbols: list[Symbol]
) -> list[dict[str, Any]]:
    candidate_by_name = {item.name: item for item in candidate_symbols}
    grouped: dict[tuple[str, str], list[Symbol]] = collections.defaultdict(list)
    for symbol in reference_symbols:
        if symbol.address_space == "C" and symbol.name in candidate_by_name:
            grouped[(symbol.module.lower(), symbol.segment)].append(symbol)
    comparisons = []
    for (module, segment), symbols in sorted(grouped.items()):
        unique_names = {item.name for item in symbols}
        if len(unique_names) < 2:
            continue
        reference_order = [
            item.name for item in sorted(symbols, key=lambda item: (item.address, item.name))
        ]
        candidate_order = sorted(
            reference_order,
            key=lambda name: (candidate_by_name[name].address, name),
        )
        comparisons.append(
            {
                "id": f"symbol-order:{module}:{segment}",
                "module": module,
                "segment": segment,
                "classification": "same-order"
                if reference_order == candidate_order
                else "reordered",
                "reference_order": reference_order,
                "candidate_order": candidate_order,
            }
        )
    return comparisons


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def markdown_report(report: dict[str, Any], queue: list[dict[str, Any]]) -> str:
    release = report["reference"]["release"]
    counts = report["summary"]
    lines = [
        "# Automated MOS binary comparison",
        "",
        f"Reference: official `{release['tag']}` at `{release['commit']}` "
        f"(`{report['reference']['binary']['sha256']}`).",
        "",
        f"Candidate: `{report['candidate']['binary']['sha256']}` "
        f"({report['candidate']['binary']['size']} bytes).",
        "",
        "This report is generated. A classification is an evidence label, not a",
        "claim of whole-program semantic equivalence.",
        "",
        "## Summary",
        "",
        f"- ZDS external symbols: {counts['zds_external_symbols']}",
        f"- Candidate defined symbols: {counts['candidate_defined_symbols']}",
        f"- Exact-name symbol pairs: {counts['shared_symbols']}",
        f"- Matched source-module ranges: {counts['matched_module_ranges']}",
        f"- Complete assembly slices compared: {counts['assembly_slices']}",
        f"- Handwritten assembly bytes covered: {counts['assembly_reference_bytes']}",
        f"- C external-anchor ranges inventoried: {counts['c_anchor_ranges']}",
        f"- Manual-review queue entries: {len(queue)}",
        "",
        "## Source divergence from the release",
        "",
    ]
    for change in report["source_divergence"]:
        lines.append(f"- `{change['status']}` `{change['path']}`")
    if not report["source_divergence"]:
        lines.append("- None")
    lines += ["", "## Deliberate preparation changes", ""]
    for change in report["preparation_changes"]:
        lines.append(f"- `{change['path']}`")
    if not report["preparation_changes"]:
        lines.append("- None")
    lines += [
        "",
        "## Matched module ranges",
        "",
        "| Module | Segment | ZDS size | AgonDev size | Classification | Confidence |",
        "|---|---:|---:|---:|---|---|",
    ]
    for item in report["module_comparisons"]:
        lines.append(
            f"| `{item['object_name']}` | `{item['segment']}` | "
            f"{item['reference']['size']} | {item['candidate']['size']} | "
            f"{item['classification']} | {item['confidence']} |"
        )
    lines += ["", "## Bounded manual-review queue", ""]
    for item in queue:
        lines.append(
            f"- **{item['priority']}** `{item['id']}` — {item['classification']}: "
            f"{item['reason']}"
        )
    if not queue:
        lines.append("- Empty")
    lines += [
        "",
        "Machine-readable evidence is in `report.json`; `review-queue.json` contains",
        "only cases not established as exact or relocation-normalized.",
        "",
    ]
    return "\n".join(lines)


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    reference_manifest = load_json(args.reference_manifest.resolve())
    reference_dir = args.reference_dir.resolve()
    candidate_dir = args.candidate_dir.resolve()
    output = args.output.resolve()
    objdump = args.toolchain.resolve() / "bin" / "ez80-none-elf-objdump"
    require_regular(objdump, "AgonDev objdump")

    reference_binary = reference_dir / "MOS.bin"
    reference_hex = reference_dir / "MOS.hex"
    reference_map = reference_dir / "MOS.map"
    candidate_binary = candidate_dir / "MOS.bin"
    candidate_map = candidate_dir / "MOS.map"
    candidate_nm = candidate_dir / "linked.nm"
    candidate_manifest = candidate_dir / "manifest.json"
    provenance_file = candidate_dir / "source-provenance.json"
    preparation_diff_file = candidate_dir / "preparation-diff.json"
    for path, description in (
        (reference_binary, "reference binary"),
        (reference_map, "reference map"),
        (reference_hex, "reference hex"),
        (candidate_binary, "candidate binary"),
        (candidate_map, "candidate map"),
        (candidate_nm, "candidate symbol table"),
        (candidate_manifest, "candidate artifact manifest"),
        (provenance_file, "candidate source provenance"),
        (preparation_diff_file, "candidate preparation diff"),
    ):
        require_regular(path, description)

    for name in ("MOS.bin", "MOS.hex", "MOS.map"):
        path = reference_dir / name
        entry = reference_manifest["assets"][name]
        if path.stat().st_size != entry["size"] or sha256_file(path) != entry["sha256"]:
            raise AnalysisError(f"pinned reference artifact drift: {name}")

    artifact_manifest = load_json(candidate_manifest)
    declared_candidate_paths: set[str] = set()
    for entry in artifact_manifest.get("files", []):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise AnalysisError("candidate artifact manifest contains an invalid entry")
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise AnalysisError("candidate artifact manifest contains an unsafe path")
        if entry["path"] in declared_candidate_paths:
            raise AnalysisError("candidate artifact manifest contains a duplicate path")
        declared_candidate_paths.add(entry["path"])
        path = candidate_dir.joinpath(*relative.parts)
        require_regular(path, "candidate manifest file")
        if path.stat().st_size != entry["size"] or sha256_file(path) != entry["sha256"]:
            raise AnalysisError(f"candidate artifact drift: {entry['path']}")
    artifact_paths = list(candidate_dir.rglob("*"))
    unsafe_artifacts = [path for path in artifact_paths if path.is_symlink()]
    if unsafe_artifacts:
        raise AnalysisError(f"candidate artifact tree contains a symlink: {unsafe_artifacts[0]}")
    actual_candidate_paths = {
        path.relative_to(candidate_dir).as_posix()
        for path in artifact_paths
        if path.is_file() and path.name != "manifest.json"
    }
    if actual_candidate_paths != declared_candidate_paths:
        missing = sorted(declared_candidate_paths - actual_candidate_paths)
        extra = sorted(actual_candidate_paths - declared_candidate_paths)
        raise AnalysisError(
            f"candidate artifact inventory drift: missing={missing}, extra={extra}"
        )

    zds_modules, zds_symbols, zds_metadata = parse_zds_map(
        reference_map.read_text(encoding="utf-8")
    )
    candidate_ranges = parse_gnu_map(candidate_map.read_text(encoding="utf-8"))
    candidate_symbols = parse_nm(candidate_nm.read_text(encoding="utf-8"))
    reference_tokens, candidate_tokens, shared = shared_symbol_tokens(
        zds_symbols, candidate_symbols
    )
    paired_names: dict[tuple[int, int], list[str]] = collections.defaultdict(list)
    for name, addresses in shared.items():
        paired_names[addresses].append(name)
    paired_tokens = {
        addresses: "@" + min(names, key=lambda name: (len(name), name))
        for addresses, names in paired_names.items()
    }
    for module_range in zds_modules:
        if module_range.source_kind != "file" or not module_range.size:
            continue
        candidate_module_range = candidate_range_for(
            module_range, candidate_ranges, zds_modules
        )
        if candidate_module_range is not None and candidate_module_range.size:
            paired_tokens.setdefault(
                (module_range.address, candidate_module_range.address),
                f"@module:{module_range.stem}:{module_range.segment}",
            )
    divergences = source_divergence(
        args.source_repo.resolve(), reference_manifest["release"]["commit"]
    )
    divergent_basenames = {Path(item["path"]).stem.lower() for item in divergences}
    preparation_diff = load_json(preparation_diff_file)
    preparation_changes = preparation_diff.get("changes")
    if not isinstance(preparation_changes, list):
        raise AnalysisError("candidate preparation diff has no changes list")

    module_comparisons = []
    module_inventory: list[dict[str, Any]] = []
    range_lookup: dict[tuple[str, str], tuple[ModuleRange, CandidateRange]] = {}
    reference_image_size = reference_binary.stat().st_size
    candidate_image_size = candidate_binary.stat().st_size
    for reference_range in zds_modules:
        inventory_item = {
            "module": reference_range.module.replace("\\", "/"),
            "object_name": reference_range.object_name,
            "source_kind": reference_range.source_kind,
            "segment": reference_range.segment,
            "address_space": reference_range.address_space,
            "reference": {
                "address": reference_range.address,
                "size": reference_range.size,
            },
        }
        if reference_range.source_kind != "file":
            inventory_item["status"] = "reference-zds-library"
            module_inventory.append(inventory_item)
            continue
        if reference_range.address_space != "C":
            inventory_item["status"] = "non-rom-address-space"
            module_inventory.append(inventory_item)
            continue
        candidate_range = candidate_range_for(reference_range, candidate_ranges, zds_modules)
        if candidate_range is None:
            inventory_item["status"] = "no-unique-candidate-range"
            module_inventory.append(inventory_item)
            continue
        inventory_item["candidate"] = {
            "address": candidate_range.address,
            "size": candidate_range.size,
            "section": candidate_range.section,
            "object_path": candidate_range.object_path,
        }
        if not reference_range.size or not candidate_range.size:
            inventory_item["status"] = "empty-range"
            module_inventory.append(inventory_item)
            continue
        if reference_range.end > reference_image_size or candidate_range.end > candidate_image_size:
            inventory_item["status"] = "outside-load-image"
            module_inventory.append(inventory_item)
            continue
        inventory_item["status"] = "compared"
        module_inventory.append(inventory_item)
        range_lookup[(reference_range.stem, reference_range.segment)] = (
            reference_range,
            candidate_range,
        )
        is_assembly = reference_range.module.lower().endswith(".asm")
        if reference_range.segment in EXECUTABLE_SEGMENTS and is_assembly:
            classification = "pending-slice-analysis"
            confidence = "none"
            reason = "assembly-module-will-be-partitioned-at-shared-symbols"
            details = {}
        elif reference_range.module.lower().endswith(".c"):
            classification = "compiler-codegen-different"
            confidence = "none"
            reason = "different-c-compiler-no-semantic-equivalence-claim"
            details = {
                "reference_size": reference_range.size,
                "candidate_size": candidate_range.size,
            }
        else:
            reference_data = reference_binary.read_bytes()[
                reference_range.address : reference_range.end
            ]
            candidate_data = candidate_binary.read_bytes()[
                candidate_range.address : candidate_range.end
            ]
            if reference_data == candidate_data:
                classification = "exact"
                confidence = "high"
                reason = "bytes-identical"
            else:
                classification = "unexplained-data"
                confidence = "none"
                reason = "module-data-bytes-differ"
            details = {
                "reference_size": len(reference_data),
                "candidate_size": len(candidate_data),
            }
        item = {
            "id": f"module:{reference_range.stem}:{reference_range.segment}",
            "module": reference_range.module.replace("\\", "/"),
            "object_name": reference_range.object_name,
            "segment": reference_range.segment,
            "classification": classification,
            "confidence": confidence,
            "reason": reason,
            "reference": {"address": reference_range.address, "size": reference_range.size},
            "candidate": {"address": candidate_range.address, "size": candidate_range.size},
            "details": details,
        }
        module_comparisons.append(item)

    # Partition every matched executable handwritten-assembly module at shared
    # external symbols. Including explicit module-start and module-end bounds
    # proves complete byte coverage while keeping any unexplained comparison
    # narrow enough to review without inspecting the whole binary manually.
    candidate_by_name = {item.name: item for item in candidate_symbols}
    assembly_slices: list[dict[str, Any]] = []
    zds_by_module_segment: dict[tuple[str, str], list[Symbol]] = collections.defaultdict(list)
    for symbol in zds_symbols:
        if symbol.address_space == "C":
            zds_by_module_segment[(symbol.module.lower(), symbol.segment)].append(symbol)
    for (module, segment), (reference_range, candidate_range) in sorted(range_lookup.items()):
        if (
            not reference_range.module.lower().endswith(".asm")
            or segment not in EXECUTABLE_SEGMENTS
        ):
            continue
        unique_by_address: dict[int, Symbol] = {}
        for symbol in sorted(
            zds_by_module_segment.get((module, segment), []),
            key=lambda item: (item.address, item.name),
        ):
            candidate_symbol = candidate_by_name.get(symbol.name)
            if (
                reference_range.address < symbol.address < reference_range.end
                and candidate_symbol is not None
                and candidate_range.address < candidate_symbol.address < candidate_range.end
            ):
                unique_by_address.setdefault(symbol.address, symbol)
        boundaries: list[tuple[str, int, int]] = [
            ("<module-start>", reference_range.address, candidate_range.address)
        ]
        invalid_boundary: dict[str, Any] | None = None
        for symbol in sorted(unique_by_address.values(), key=lambda item: item.address):
            candidate_address = candidate_by_name[symbol.name].address
            previous = boundaries[-1]
            if symbol.address <= previous[1] or candidate_address <= previous[2]:
                invalid_boundary = {
                    "symbol": symbol.name,
                    "reference_address": symbol.address,
                    "candidate_address": candidate_address,
                    "previous_reference_address": previous[1],
                    "previous_candidate_address": previous[2],
                }
                break
            boundaries.append((symbol.name, symbol.address, candidate_address))
        boundaries.append(("<module-end>", reference_range.end, candidate_range.end))
        if (
            invalid_boundary is not None
            or boundaries[-1][1] <= boundaries[-2][1]
            or boundaries[-1][2] <= boundaries[-2][2]
        ):
            assembly_slices.append(
                {
                    "id": f"slice:{module}:{segment}:invalid-boundaries",
                    "module": module,
                    "segment": segment,
                    "start_symbol": "<module-start>",
                    "end_symbol": "<module-end>",
                    "classification": "unexplained",
                    "confidence": "none",
                    "reason": "shared-symbol-order-or-range-differs",
                    "reference": {
                        "address": reference_range.address,
                        "size": reference_range.size,
                    },
                    "candidate": {
                        "address": candidate_range.address,
                        "size": candidate_range.size,
                    },
                    "details": invalid_boundary or {},
                }
            )
            continue
        for left, right in zip(boundaries, boundaries[1:]):
            left_name, reference_start, candidate_start = left
            right_name, reference_end, candidate_end = right
            classification, confidence, reason, details = compare_executable_range(
                objdump=objdump,
                reference_binary=reference_binary,
                candidate_binary=candidate_binary,
                reference_start=reference_start,
                reference_end=reference_end,
                candidate_start=candidate_start,
                candidate_end=candidate_end,
                reference_tokens=reference_tokens,
                candidate_tokens=candidate_tokens,
                paired_tokens=paired_tokens,
                reference_context=(reference_range.address, reference_range.end),
                candidate_context=(candidate_range.address, candidate_range.end),
            )
            if classification == "unexplained" and module in divergent_basenames:
                classification = "explained-source-divergence"
                confidence = "high"
                reason = "maintained-source-changed-since-official-release"
            assembly_slices.append(
                {
                    "id": f"slice:{module}:{segment}:{left_name}..{right_name}",
                    "module": module,
                    "segment": segment,
                    "start_symbol": left_name,
                    "end_symbol": right_name,
                    "classification": classification,
                    "confidence": confidence,
                    "reason": reason,
                    "reference": {
                        "address": reference_start,
                        "size": reference_end - reference_start,
                    },
                    "candidate": {
                        "address": candidate_start,
                        "size": candidate_end - candidate_start,
                    },
                    "details": details,
                }
            )

    slices_by_module: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for item in assembly_slices:
        slices_by_module[(item["module"], item["segment"])].append(item)
    for item in module_comparisons:
        key = (Path(item["module"]).stem.lower(), item["segment"])
        slices = slices_by_module.get(key)
        if item["classification"] != "pending-slice-analysis" or not slices:
            continue
        classifications = {part["classification"] for part in slices}
        if classifications == {"exact"}:
            item.update(
                classification="exact",
                confidence="high",
                reason="all-module-slices-byte-identical",
            )
        elif classifications <= {"exact", "relocation-only", "instruction-equivalent"}:
            item.update(
                classification="relocation-only",
                confidence="medium",
                reason="all-module-slices-exact-or-address-normalized",
            )
        elif classifications <= {
            "exact",
            "relocation-only",
            "instruction-equivalent",
            "explained-source-divergence",
        }:
            item.update(
                classification="explained-source-divergence",
                confidence="high",
                reason="only-nonrelocation-difference-is-maintained-source-divergence",
            )
        else:
            item.update(
                classification="unexplained",
                confidence="none",
                reason="one-or-more-assembly-slices-remain-unexplained",
            )
        item["details"] = {
            "slice_count": len(slices),
            "slice_classifications": dict(
                sorted(collections.Counter(part["classification"] for part in slices).items())
            ),
        }

    # The release map exposes external C anchors but not private/static
    # function boundaries. Compare every safe external anchor against the exact
    # sized AgonDev symbol and retain the boundary basis explicitly. This can
    # prove an occasional identical instruction body, but unequal/different
    # compiler output remains evidence only and is never guessed equivalent.
    c_anchor_comparisons: list[dict[str, Any]] = []
    for (module, segment), (reference_range, candidate_range) in sorted(range_lookup.items()):
        if not reference_range.module.lower().endswith(".c") or segment not in EXECUTABLE_SEGMENTS:
            continue
        symbols = [
            symbol
            for symbol in zds_by_module_segment.get((module, segment), [])
            if symbol.name in candidate_by_name
            and candidate_by_name[symbol.name].size > 0
            and candidate_by_name[symbol.name].symbol_type.lower() == "t"
        ]
        unique_by_address: dict[int, Symbol] = {}
        for symbol in sorted(symbols, key=lambda item: (item.address, item.name)):
            unique_by_address.setdefault(symbol.address, symbol)
        ordered = sorted(unique_by_address.values(), key=lambda item: item.address)
        for index, symbol in enumerate(ordered):
            candidate_symbol = candidate_by_name[symbol.name]
            reference_end = (
                ordered[index + 1].address if index + 1 < len(ordered) else reference_range.end
            )
            candidate_end = candidate_symbol.address + candidate_symbol.size
            if (
                reference_end <= symbol.address
                or candidate_end <= candidate_symbol.address
                or reference_end > reference_range.end
                or not (
                    candidate_range.address
                    <= candidate_symbol.address
                    < candidate_end
                    <= candidate_range.end
                )
            ):
                continue
            classification, confidence, reason, details = compare_executable_range(
                objdump=objdump,
                reference_binary=reference_binary,
                candidate_binary=candidate_binary,
                reference_start=symbol.address,
                reference_end=reference_end,
                candidate_start=candidate_symbol.address,
                candidate_end=candidate_end,
                reference_tokens=reference_tokens,
                candidate_tokens=candidate_tokens,
                paired_tokens=paired_tokens,
                reference_context=(reference_range.address, reference_range.end),
                candidate_context=(candidate_range.address, candidate_range.end),
            )
            if classification == "instruction-equivalent":
                classification = "semantically-equivalent-codegen"
                confidence = "medium"
                reason = "bounded-disassembly-instruction-stream-identical"
            elif classification == "unexplained":
                classification = "compiler-codegen-different"
                confidence = "none"
                reason = "different-c-compiler-no-semantic-equivalence-claim"
            c_anchor_comparisons.append(
                {
                    "id": f"c-anchor:{module}:{symbol.name}",
                    "module": module,
                    "segment": segment,
                    "symbol": symbol.name,
                    "classification": classification,
                    "confidence": confidence,
                    "reason": reason,
                    "reference": {
                        "address": symbol.address,
                        "size": reference_end - symbol.address,
                        "boundary": "next-external-anchor-or-module-end",
                    },
                    "candidate": {
                        "address": candidate_symbol.address,
                        "size": candidate_symbol.size,
                        "boundary": "ELF-symbol-size",
                    },
                    "details": details,
                }
            )

    queue: list[dict[str, Any]] = []
    for item in assembly_slices:
        if item["classification"] == "unexplained":
            queue.append(
                {
                    "id": item["id"],
                    "priority": "high",
                    "classification": item["classification"],
                    "reason": item["reason"],
                    "evidence": {
                        "reference": item["reference"],
                        "candidate": item["candidate"],
                    },
                }
            )
    for item in module_comparisons:
        if item["classification"] in {
            "exact",
            "relocation-only",
            "instruction-equivalent",
            "pending-slice-analysis",
        }:
            continue
        if item["classification"] == "unexplained" and item["module"].lower().endswith(".asm"):
            continue
        queue.append(
            {
                "id": item["id"],
                "priority": "medium",
                "classification": item["classification"],
                "reason": item["reason"],
                "evidence": {
                    "reference": item["reference"],
                    "candidate": item["candidate"],
                },
            }
        )

    module_comparisons.sort(key=lambda item: (item["reference"]["address"], item["id"]))
    module_inventory.sort(
        key=lambda item: (
            item["address_space"],
            item["reference"]["address"],
            item["module"],
            item["segment"],
        )
    )
    assembly_slices.sort(
        key=lambda item: (item["reference"]["address"], item["id"])
    )
    c_anchor_comparisons.sort(
        key=lambda item: (item["reference"]["address"], item["id"])
    )
    queue.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2}[item["priority"]], item["id"]))
    provenance = load_json(provenance_file)
    assembly_reference_bytes = sum(item["reference"]["size"] for item in assembly_slices)
    assembly_candidate_bytes = sum(item["candidate"]["size"] for item in assembly_slices)
    expected_assembly_bytes = sum(
        item["reference"]["size"]
        for item in module_comparisons
        if item["module"].lower().endswith(".asm")
        and item["segment"] in EXECUTABLE_SEGMENTS
    )
    if assembly_reference_bytes != expected_assembly_bytes:
        raise AnalysisError(
            "assembly slices do not cover all matched executable assembly bytes"
        )
    reference_bytes = reference_binary.read_bytes()
    candidate_bytes = candidate_binary.read_bytes()
    symbol_deltas = collections.Counter(
        candidate_address - reference_address
        for reference_address, candidate_address in shared.values()
    )
    order_comparisons = symbol_order_comparisons(zds_symbols, candidate_symbols)
    report = {
        "schema": 1,
        "reference": {
            "release": reference_manifest["release"],
            "build": zds_metadata,
            "binary": {
                "size": reference_binary.stat().st_size,
                "sha256": sha256_file(reference_binary),
            },
            "map_sha256": sha256_file(reference_map),
        },
        "candidate": {
            "source": provenance.get("source"),
            "binary": {
                "size": candidate_binary.stat().st_size,
                "sha256": sha256_file(candidate_binary),
            },
            "elf_sha256": sha256_file(candidate_dir / "MOS.elf"),
            "map_sha256": sha256_file(candidate_map),
            "artifact_manifest_sha256": sha256_file(candidate_manifest),
        },
        "source_divergence": divergences,
        "preparation_changes": preparation_changes,
        "raw_image_difference": binary_difference_summary(reference_bytes, candidate_bytes),
        "symbol_address_deltas": [
            {"delta": delta, "symbol_count": count}
            for delta, count in sorted(
                symbol_deltas.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "summary": {
            "zds_module_ranges": len(zds_modules),
            "zds_external_symbols": len(zds_symbols),
            "candidate_input_ranges": len(candidate_ranges),
            "candidate_defined_symbols": len(candidate_symbols),
            "shared_symbols": len(shared),
            "matched_module_ranges": len(module_comparisons),
            "zds_module_inventory_status": dict(
                sorted(collections.Counter(item["status"] for item in module_inventory).items())
            ),
            "assembly_slices": len(assembly_slices),
            "assembly_reference_bytes": assembly_reference_bytes,
            "assembly_candidate_bytes": assembly_candidate_bytes,
            "assembly_comparison_sha256": stable_comparison_digest(assembly_slices),
            "module_comparison_sha256": stable_comparison_digest(module_comparisons),
            "c_anchor_comparison_sha256": stable_comparison_digest(c_anchor_comparisons),
            "review_queue_entries": len(queue),
            "high_priority_review_entries": sum(
                item["priority"] == "high" for item in queue
            ),
            "symbol_order_modules": len(order_comparisons),
            "reordered_symbol_modules": sum(
                item["classification"] == "reordered" for item in order_comparisons
            ),
            "c_anchor_ranges": len(c_anchor_comparisons),
            "c_anchor_classifications": dict(
                sorted(
                    collections.Counter(
                        item["classification"] for item in c_anchor_comparisons
                    ).items()
                )
            ),
            "module_classifications": dict(
                sorted(collections.Counter(item["classification"] for item in module_comparisons).items())
            ),
            "assembly_slice_classifications": dict(
                sorted(collections.Counter(item["classification"] for item in assembly_slices).items())
            ),
        },
        "module_comparisons": module_comparisons,
        "zds_module_inventory": module_inventory,
        "assembly_slices": assembly_slices,
        "c_anchor_comparisons": c_anchor_comparisons,
        "symbol_order_comparisons": order_comparisons,
    }
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise AnalysisError(f"report output may not be a symlink: {output}")
    write_json(output / "report.json", report)
    write_json(output / "review-queue.json", {"schema": 1, "items": queue})
    (output / "report.md").write_text(markdown_report(report, queue), encoding="utf-8")
    (output / "reference.disassembly.txt").write_text(
        raw_disassembly_text(objdump, reference_binary), encoding="utf-8"
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-manifest", type=Path, default=DEFAULT_REFERENCE_MANIFEST)
    parser.add_argument("--reference-dir", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    parser.add_argument("--source-repo", type=Path, default=DEFAULT_SOURCE_REPO)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        report = analyze(parse_args(argv))
        summary = report["summary"]
        print(
            "binary comparison generated: "
            f"{summary['shared_symbols']} shared symbols, "
            f"{summary['matched_module_ranges']} module ranges, "
            f"{summary['assembly_slices']} complete assembly slices"
        )
        return 0
    except (AnalysisError, OSError, UnicodeDecodeError, KeyError, ValueError) as exc:
        print(f"analysis error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
