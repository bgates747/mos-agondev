#!/usr/bin/env python3
"""Inventory MOS printf/sprintf formats and enforce the firmware contract."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FormatUse:
    source: str
    line: int
    function: str
    format: str


@dataclass(frozen=True)
class FormatSpecifier:
    spelling: str
    flags: str
    length: str
    conversion: str


def strip_comments(source: str) -> str:
    result = list(source)
    index = 0
    state = "code"
    while index < len(source):
        current = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if current == '"':
                state = "string"
            elif current == "'":
                state = "character"
            elif current == "/" and following == "/":
                result[index] = result[index + 1] = " "
                index += 1
                state = "line-comment"
            elif current == "/" and following == "*":
                result[index] = result[index + 1] = " "
                index += 1
                state = "block-comment"
        elif state in {"string", "character"}:
            if current == "\\":
                index += 1
            elif (state == "string" and current == '"') or (
                state == "character" and current == "'"
            ):
                state = "code"
        elif state == "line-comment":
            if current == "\n":
                state = "code"
            else:
                result[index] = " "
        elif state == "block-comment":
            if current == "*" and following == "/":
                result[index] = result[index + 1] = " "
                index += 1
                state = "code"
            elif current != "\n":
                result[index] = " "
        index += 1
    return "".join(result)


def call_arguments(source: str, opening_parenthesis: int) -> tuple[list[str], int]:
    arguments: list[str] = []
    start = opening_parenthesis + 1
    index = start
    depth = 0
    state = "code"
    while index < len(source):
        current = source[index]
        if state == "code":
            if current == '"':
                state = "string"
            elif current == "'":
                state = "character"
            elif current in "([{":
                depth += 1
            elif current in ")]}":
                if current == ")" and depth == 0:
                    arguments.append(source[start:index])
                    return arguments, index
                depth -= 1
            elif current == "," and depth == 0:
                arguments.append(source[start:index])
                start = index + 1
        else:
            if current == "\\":
                index += 1
            elif (state == "string" and current == '"') or (
                state == "character" and current == "'"
            ):
                state = "code"
        index += 1
    raise ValueError("unterminated function call")


STRING_TOKEN = re.compile(r'(?:u8|[LuU])?"(?:\\.|[^"\\])*"')
GOLDEN_PATTERN = re.compile(r'GOLDEN_PATTERN\(\s*"(?P<pattern>(?:\\.|[^"\\])*)"\s*\)')


def decode_string_argument(argument: str) -> str | None:
    position = 0
    pieces: list[str] = []
    while position < len(argument):
        whitespace = re.match(r"\s*", argument[position:])
        assert whitespace is not None
        position += whitespace.end()
        if position == len(argument):
            break
        match = STRING_TOKEN.match(argument, position)
        if not match:
            return None
        token = match.group(0)
        token = re.sub(r"^(?:u8|[LuU])", "", token)
        pieces.append(ast.literal_eval(token))
        position = match.end()
    return "".join(pieces) if pieces else None


def find_format_uses(
    source: str,
    source_name: str,
    format_arguments: dict[str, int],
) -> tuple[list[FormatUse], list[str]]:
    cleaned = strip_comments(source)
    names = "|".join(re.escape(name) for name in format_arguments)
    call_pattern = re.compile(rf"\b(?P<name>{names})\s*\(")
    uses: list[FormatUse] = []
    errors: list[str] = []
    for match in call_pattern.finditer(cleaned):
        function = match.group("name")
        opening = cleaned.find("(", match.start())
        arguments, _ = call_arguments(cleaned, opening)
        format_index = format_arguments[function]
        line = cleaned.count("\n", 0, match.start()) + 1
        if len(arguments) <= format_index:
            errors.append(f"{source_name}:{line}: missing format argument")
            continue
        decoded = decode_string_argument(arguments[format_index])
        if decoded is None:
            errors.append(f"{source_name}:{line}: format is not a string literal")
            continue
        uses.append(FormatUse(source_name, line, function, decoded))
    return uses, errors


def parse_specifiers(format_string: str) -> list[FormatSpecifier]:
    result: list[FormatSpecifier] = []
    index = 0
    while index < len(format_string):
        if format_string[index] != "%":
            index += 1
            continue
        start = index
        index += 1
        if index < len(format_string) and format_string[index] == "%":
            result.append(FormatSpecifier("%%", "", "", "%"))
            index += 1
            continue
        flags_start = index
        while index < len(format_string) and format_string[index] in "-+ #0":
            index += 1
        flags = format_string[flags_start:index]
        if index < len(format_string) and format_string[index] == "*":
            index += 1
        else:
            while index < len(format_string) and format_string[index].isdigit():
                index += 1
        if index < len(format_string) and format_string[index] == ".":
            index += 1
            if index < len(format_string) and format_string[index] == "*":
                index += 1
            else:
                while index < len(format_string) and format_string[index].isdigit():
                    index += 1
        length = ""
        for candidate in ("hh", "ll", "h", "l", "j", "z", "t", "L"):
            if format_string.startswith(candidate, index):
                length = candidate
                index += len(candidate)
                break
        if index >= len(format_string):
            raise ValueError(f"incomplete format specifier at offset {start}")
        conversion = format_string[index]
        index += 1
        result.append(
            FormatSpecifier(format_string[start:index], flags, length, conversion)
        )
    return result


def golden_patterns(source: str) -> list[str]:
    """Return the formatter spellings explicitly exercised by host goldens."""
    return [
        ast.literal_eval('"' + match.group("pattern") + '"')
        for match in GOLDEN_PATTERN.finditer(strip_comments(source))
    ]


def check_golden_coverage(report: dict[str, object], source: str) -> list[str]:
    used = set(report["specifiers"])
    marked = golden_patterns(source)
    errors: list[str] = []
    duplicates = sorted(pattern for pattern, count in Counter(marked).items() if count > 1)
    missing = sorted(used - set(marked))
    extra = sorted(set(marked) - used)
    if duplicates:
        errors.append("duplicate formatter golden markers: " + ", ".join(duplicates))
    if missing:
        errors.append("used formatter spellings lack host goldens: " + ", ".join(missing))
    if extra:
        errors.append("host golden markers are not used by MOS: " + ", ".join(extra))
    return errors


def scan(
    source_root: Path, policy: dict[str, object]
) -> tuple[dict[str, object], list[str]]:
    contract = policy["formatter_contract"]
    format_arguments = {
        name: int(index) for name, index in contract["format_arguments"].items()
    }
    uses: list[FormatUse] = []
    errors: list[str] = []
    sources = [source_root / "main.c"] + sorted((source_root / "src").glob("*.c"))
    for source in sources:
        found, source_errors = find_format_uses(
            source.read_text(encoding="utf-8"),
            str(source.relative_to(source_root)),
            format_arguments,
        )
        uses.extend(found)
        errors.extend(source_errors)

    specifications: list[FormatSpecifier] = []
    for use in uses:
        try:
            parsed = parse_specifiers(use.format)
        except ValueError as error:
            errors.append(f"{use.source}:{use.line}: {error}")
            continue
        specifications.extend(parsed)
        for specifier in parsed:
            disallowed_flags = set(specifier.flags) - set(contract["allowed_flags"])
            if disallowed_flags:
                errors.append(
                    f"{use.source}:{use.line}: unsupported flags in {specifier.spelling}"
                )
            if specifier.length not in contract["allowed_length_modifiers"]:
                errors.append(
                    f"{use.source}:{use.line}: unsupported length in {specifier.spelling}"
                )
            if specifier.conversion not in contract["allowed_conversions"]:
                errors.append(
                    f"{use.source}:{use.line}: unsupported conversion in {specifier.spelling}"
                )

    return {
        "call_count": len(uses),
        "specifier_count": len(specifications),
        "functions": dict(sorted(Counter(use.function for use in uses).items())),
        "specifiers": dict(
            sorted(Counter(spec.spelling for spec in specifications).items())
        ),
        "length_modifiers": dict(
            sorted(Counter(spec.length for spec in specifications).items())
        ),
        "conversions": dict(
            sorted(Counter(spec.conversion for spec in specifications).items())
        ),
    }, errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    runtime_root = Path(__file__).resolve().parent
    repository = runtime_root.parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=repository / "projects/mos-port/worktree",
    )
    parser.add_argument(
        "--policy", type=Path, default=runtime_root / "runtime_policy.json"
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    report, errors = scan(args.source.resolve(), policy)
    golden_source = (
        Path(__file__).resolve().parent / "formatter/host_golden.c"
    ).read_text(encoding="utf-8")
    errors.extend(check_golden_coverage(report, golden_source))
    if args.json:
        print(json.dumps({"errors": errors, **report}, indent=2, sort_keys=True))
    else:
        print(
            f"formats: {report['call_count']} calls, "
            f"{report['specifier_count']} conversion specifiers"
        )
        print(f"conversions: {report['conversions']}")
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
