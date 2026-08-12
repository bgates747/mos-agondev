#!/usr/bin/env python3
"""Compare local split i48 stubs with the pinned AgonDev archive member."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def symbol_ranges(nm: Path, target: Path) -> dict[str, tuple[int, int | None]]:
    output = subprocess.run(
        [str(nm), "-P", str(target)], check=True, text=True, capture_output=True
    ).stdout
    text_symbols: list[tuple[str, int]] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[1].upper() == "T":
            text_symbols.append((fields[0], int(fields[2], 16)))
    result: dict[str, tuple[int, int | None]] = {}
    addresses = sorted({address for _, address in text_symbols})
    for name, address in text_symbols:
        following = next((candidate for candidate in addresses if candidate > address), None)
        result[name] = (address, following)
    return result


def function_bytes(
    nm: Path, objdump: Path, target: Path, symbol: str
) -> bytes:
    ranges = symbol_ranges(nm, target)
    if symbol not in ranges:
        raise ValueError(f"{target} does not define {symbol}")
    start, end = ranges[symbol]
    output = subprocess.run(
        [str(objdump), "-d", str(target)], check=True, text=True, capture_output=True
    ).stdout
    result = bytearray()
    for line in output.splitlines():
        match = re.match(r"\s*([0-9A-Fa-f]+):\s+((?:[0-9A-Fa-f]{2}\s+)+)", line)
        if not match:
            continue
        address = int(match.group(1), 16)
        if address >= start and (end is None or address < end):
            result.extend(bytes.fromhex(match.group(2)))
    if not result:
        raise ValueError(f"could not extract bytes for {symbol} from {target}")
    return bytes(result)


def verify(
    ar: Path,
    nm: Path,
    objdump: Path,
    archive: Path,
    local: Path,
) -> dict[str, str]:
    archive_object = subprocess.run(
        [str(ar), "p", str(archive), "i48stubs.o"],
        check=True,
        capture_output=True,
    ).stdout
    if not archive_object:
        raise ValueError("i48stubs.o is absent or empty")
    with tempfile.NamedTemporaryFile(suffix=".o") as temporary:
        temporary.write(archive_object)
        temporary.flush()
        reference = Path(temporary.name)
        result: dict[str, str] = {}
        for symbol in ("__i48mulu", "__i48shru"):
            expected = function_bytes(nm, objdump, reference, symbol)
            observed = function_bytes(nm, objdump, local, symbol)
            if observed != expected:
                raise ValueError(
                    f"{symbol} differs: expected {expected.hex()}, got {observed.hex()}"
                )
            result[symbol] = observed.hex()
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    runtime_root = Path(__file__).resolve().parent
    repository = runtime_root.parents[2]
    toolbin = repository / "toolchains/agondev/bin"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ar", type=Path, default=toolbin / "ez80-none-elf-ar")
    parser.add_argument("--nm", type=Path, default=toolbin / "ez80-none-elf-nm")
    parser.add_argument(
        "--objdump", type=Path, default=toolbin / "ez80-none-elf-objdump"
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=repository / "toolchains/agondev/lib/libagon.a",
    )
    parser.add_argument(
        "--local", type=Path, default=runtime_root / "build/i48_required.o"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = verify(
            args.ar.resolve(),
            args.nm.resolve(),
            args.objdump.resolve(),
            args.archive.resolve(),
            args.local.resolve(),
        )
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        "split i48 helpers match pinned i48stubs.o: "
        + ", ".join(f"{name}={data}" for name, data in result.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
