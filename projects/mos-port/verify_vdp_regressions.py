#!/usr/bin/env python3
"""Verify linked VDP startup and oversized-packet behavior.

The oversized-packet check executes the relevant instructions from the flat
firmware image with a deliberately small eZ80 ADL interpreter.  It therefore
tests the bytes that will be deployed, rather than a second implementation of
the protocol parser.  The interpreter implements only the opcodes reached by
the protocol state machine; an unexpected instruction is a hard failure.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Sequence


MASK24 = 0xFFFFFF
BUFFER_LENGTH = 16
OVERSIZED_LENGTHS = range(BUFFER_LENGTH + 1, 256)
ZDS_REFERENCE_BIN_SHA256 = (
    "d564243283972690933a4554296ad6202ca4ef54572279533a942960846bebae"
)
ZDS_REFERENCE_MAP_SHA256 = (
    "d69e60bbce61a7b4b3eef318ba395f11c4e1a5b585755755113992dc94edcb86"
)
PROTOCOL_SYMBOLS = (
    "vdp_protocol",
    "_vdp_protocol_state",
    "_vdp_protocol_cmd",
    "_vdp_protocol_len",
    "_vdp_protocol_ptr",
    "_vdp_protocol_data",
    "_gp",
)
HANDSHAKE_SYMBOLS = (
    "_main",
    "_wait_ESP32",
    "_init_interrupts",
    "_bootmsg",
    "_gp",
)


class VdpRegressionError(RuntimeError):
    """The linked firmware violated the bounded VDP contract."""


class FirmwareImage:
    def __init__(self, label: str, rom: bytes, symbols: dict[str, int]) -> None:
        self.label = label
        self.rom = rom
        self.symbols = symbols


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VdpRegressionError(message)


def require_sha256(label: str, payload: bytes, expected: str) -> None:
    """Require exact audited bytes before interpreting a reference artifact."""
    actual = hashlib.sha256(payload).hexdigest()
    _require(
        actual == expected,
        f"{label} SHA-256 mismatch: expected {expected}, got {actual}",
    )


def parse_nm_symbols(output: str, required: tuple[str, ...]) -> dict[str, int]:
    """Extract unique required symbols from ``nm`` output."""
    wanted = set(required)
    symbols: dict[str, int] = {}
    for line in output.splitlines():
        fields = line.split(None, 2)
        if len(fields) != 3 or fields[2] not in wanted:
            continue
        name = fields[2]
        if name in symbols:
            raise VdpRegressionError(f"duplicate candidate symbol: {name}")
        try:
            symbols[name] = int(fields[0], 16)
        except ValueError as error:
            raise VdpRegressionError(f"malformed candidate symbol: {line}") from error
    missing = sorted(wanted - symbols.keys())
    _require(not missing, "candidate ELF lacks symbols: " + ", ".join(missing))
    return symbols


def parse_zds_map_symbols(output: str, required: tuple[str, ...]) -> dict[str, int]:
    """Extract the public code/data addresses from a ZDS linker map."""
    symbols: dict[str, int] = {}
    for name in required:
        matches = re.findall(
            rf"^{re.escape(name)}\s+[CD]:([0-9A-Fa-f]{{6}})\s",
            output,
            flags=re.MULTILINE,
        )
        _require(matches, f"ZDS map lacks symbol address: {name}")
        _require(len(set(matches)) == 1, f"ZDS map has conflicting addresses: {name}")
        symbols[name] = int(matches[0], 16)
    return symbols


class Ez80ProtocolMachine:
    """Tiny ADL interpreter for only the linked protocol path under test."""

    def __init__(self, image: FirmwareImage) -> None:
        self.image = image
        self.memory: dict[int, int] = {}
        self.pc = 0
        self.a = 0
        self.c = 0
        self.hl = 0
        self.de = 0
        self.zero = False
        self.carry = False

    def read8(self, address: int) -> int:
        address &= MASK24
        if address in self.memory:
            return self.memory[address]
        if address < len(self.image.rom):
            return self.image.rom[address]
        return 0

    def write8(self, address: int, value: int) -> None:
        self.memory[address & MASK24] = value & 0xFF

    def read24(self, address: int) -> int:
        return (
            self.read8(address)
            | (self.read8(address + 1) << 8)
            | (self.read8(address + 2) << 16)
        )

    def write24(self, address: int, value: int) -> None:
        for offset in range(3):
            self.write8(address + offset, value >> (8 * offset))

    def _fetch8(self, address: int) -> int:
        if not 0 <= address < len(self.image.rom):
            raise VdpRegressionError(
                f"{self.image.label}: instruction fetch outside ROM at 0x{address:06x}"
            )
        return self.image.rom[address]

    def _fetch24(self, address: int) -> int:
        return (
            self._fetch8(address)
            | (self._fetch8(address + 1) << 8)
            | (self._fetch8(address + 2) << 16)
        )

    def _relative_target(self) -> int:
        displacement = self._fetch8(self.pc + 1)
        if displacement & 0x80:
            displacement -= 0x100
        return (self.pc + 2 + displacement) & MASK24

    def call_protocol(self, value: int, buffer_address: int) -> int:
        """Invoke ``vdp_protocol`` once, as the UART ISR does for one byte."""
        self.pc = self.image.symbols["vdp_protocol"]
        self.a = 0
        self.c = value & 0xFF
        self.hl = buffer_address & MASK24
        self.de = 0
        self.zero = False
        self.carry = False

        for steps in range(1, 129):
            opcode = self._fetch8(self.pc)

            if opcode == 0x3A:  # ld a,(nn24)
                self.a = self.read8(self._fetch24(self.pc + 1))
                self.pc += 4
            elif opcode == 0xB7:  # or a,a
                self.zero = self.a == 0
                self.carry = False
                self.pc += 1
            elif opcode in (0x18, 0x20, 0x28, 0x38):  # jr; jr nz/z/c
                take = (
                    opcode == 0x18
                    or (opcode == 0x20 and not self.zero)
                    or (opcode == 0x28 and self.zero)
                    or (opcode == 0x38 and self.carry)
                )
                self.pc = self._relative_target() if take else self.pc + 2
            elif opcode == 0x3D:  # dec a
                self.a = (self.a - 1) & 0xFF
                self.zero = self.a == 0
                self.pc += 1
            elif opcode == 0xCA:  # jp z,nn24
                target = self._fetch24(self.pc + 1)
                self.pc = target if self.zero else self.pc + 4
            elif opcode == 0xAF:  # xor a,a
                self.a = 0
                self.zero = True
                self.carry = False
                self.pc += 1
            elif opcode == 0x32:  # ld (nn24),a
                self.write8(self._fetch24(self.pc + 1), self.a)
                self.pc += 4
            elif opcode == 0xC9:  # ret
                return steps
            elif opcode == 0x79:  # ld a,c
                self.a = self.c
                self.pc += 1
            elif opcode == 0xD6:  # sub a,n
                value = self._fetch8(self.pc + 1)
                result = self.a - value
                self.carry = result < 0
                self.a = result & 0xFF
                self.zero = self.a == 0
                self.pc += 2
            elif opcode in (0xC0, 0xD0, 0xD8):  # ret nz/nc/c
                take = (
                    (opcode == 0xC0 and not self.zero)
                    or (opcode == 0xD0 and not self.carry)
                    or (opcode == 0xD8 and self.carry)
                )
                if take:
                    return steps
                self.pc += 1
            elif opcode == 0x22:  # ld (nn24),hl
                self.write24(self._fetch24(self.pc + 1), self.hl)
                self.pc += 4
            elif opcode == 0x3E:  # ld a,n
                self.a = self._fetch8(self.pc + 1)
                self.pc += 2
            elif opcode == 0xFE:  # cp a,n
                value = self._fetch8(self.pc + 1)
                self.zero = self.a == value
                self.carry = self.a < value
                self.pc += 2
            elif opcode == 0x2A:  # ld hl,(nn24)
                self.hl = self.read24(self._fetch24(self.pc + 1))
                self.pc += 4
            elif opcode == 0x71:  # ld (hl),c
                self.write8(self.hl, self.c)
                self.pc += 1
            elif opcode == 0x23:  # inc hl
                self.hl = (self.hl + 1) & MASK24
                self.pc += 1
            elif opcode == 0x11:  # ld de,nn24
                self.de = self._fetch24(self.pc + 1)
                self.pc += 4
            elif opcode == 0x21:  # ld hl,nn24
                self.hl = self._fetch24(self.pc + 1)
                self.pc += 4
            elif opcode == 0x6F:  # ld l,a
                self.hl = (self.hl & 0xFFFF00) | self.a
                self.pc += 1
            elif opcode == 0x29:  # add hl,hl
                self.hl = (self.hl + self.hl) & MASK24
                self.pc += 1
            elif opcode == 0x19:  # add hl,de
                self.hl = (self.hl + self.de) & MASK24
                self.pc += 1
            elif opcode == 0xE9:  # jp (hl)
                self.pc = self.hl
            elif opcode == 0xC3:  # jp nn24
                self.pc = self._fetch24(self.pc + 1)
            else:
                raise VdpRegressionError(
                    f"{self.image.label}: unsupported opcode 0x{opcode:02x} "
                    f"at 0x{self.pc:06x}"
                )
            self.pc &= MASK24

        raise VdpRegressionError(
            f"{self.image.label}: protocol invocation exceeded 128 instructions"
        )


class ProtocolHarness:
    def __init__(self, image: FirmwareImage, sentinel: int = 0xCC) -> None:
        self.image = image
        self.machine = Ez80ProtocolMachine(image)
        self.sentinel = sentinel
        for offset in range(BUFFER_LENGTH):
            self.machine.write8(image.symbols["_vdp_protocol_data"] + offset, sentinel)
        self.machine.write8(image.symbols["_gp"], 0x5A)

    def byte(self, name: str) -> int:
        return self.machine.read8(self.image.symbols[name])

    def buffer(self) -> bytes:
        start = self.image.symbols["_vdp_protocol_data"]
        return bytes(self.machine.read8(start + offset) for offset in range(BUFFER_LENGTH))

    def feed(self, value: int) -> int:
        return self.machine.call_protocol(
            value,
            self.image.symbols["_vdp_protocol_data"],
        )

    def feed_all(self, values: bytes | list[int]) -> None:
        for value in values:
            self.feed(value)


def _verify_general_poll(harness: ProtocolHarness, context: str) -> None:
    harness.feed_all([0x80, 1, 0xA5])
    _require(harness.byte("_vdp_protocol_state") == 0, f"{context}: GP did not finish")
    _require(harness.byte("_gp") == 0xA5, f"{context}: following GP was not accepted")


def verify_oversized_packets(image: FirmwareImage) -> None:
    """Execute every possible oversized length through the linked parser."""
    for length in OVERSIZED_LENGTHS:
        harness = ProtocolHarness(image)
        harness.feed(0x81)
        _require(
            harness.byte("_vdp_protocol_state") == 1,
            f"{image.label}: command header did not enter state 1",
        )
        harness.feed(length)
        _require(
            harness.byte("_vdp_protocol_state") == 3,
            f"{image.label}: length {length} did not enter discard state",
        )
        _require(
            harness.byte("_vdp_protocol_len") == length,
            f"{image.label}: length {length} was not preserved for discard",
        )

        payload = bytes((length + index * 29) & 0xFF for index in range(length))
        for index, value in enumerate(payload):
            harness.feed(value)
            remaining = length - index - 1
            expected_state = 0 if remaining == 0 else 3
            _require(
                harness.byte("_vdp_protocol_len") == remaining,
                f"{image.label}: length {length} discard counter drifted at byte {index}",
            )
            _require(
                harness.byte("_vdp_protocol_state") == expected_state,
                f"{image.label}: length {length} discard ended at the wrong byte",
            )

        _require(
            harness.buffer() == bytes([harness.sentinel]) * BUFFER_LENGTH,
            f"{image.label}: oversized length {length} wrote the packet buffer",
        )
        _require(
            harness.byte("_gp") == 0x5A,
            f"{image.label}: oversized length {length} executed a packet handler",
        )
        _verify_general_poll(harness, f"{image.label}: after oversized length {length}")

    # Also exercise the legal boundary and its transition into a later packet.
    harness = ProtocolHarness(image)
    payload = bytes(range(BUFFER_LENGTH))
    harness.feed_all([0x8F, BUFFER_LENGTH])
    harness.feed_all(payload)
    _require(
        harness.byte("_vdp_protocol_state") == 0,
        f"{image.label}: legal 16-byte packet did not finish",
    )
    _require(
        harness.buffer() == payload,
        f"{image.label}: legal 16-byte packet did not fill the buffer exactly",
    )
    _verify_general_poll(harness, f"{image.label}: after legal 16-byte packet")


def verify_framing_boundaries(image: FirmwareImage) -> None:
    """Execute idle, recovery, partial, and every legal framing boundary."""
    harness = ProtocolHarness(image)
    idle_steps = [harness.feed(value) for value in (0x00, 0x7F, 0x42)]
    _require(
        harness.byte("_vdp_protocol_state") == 0,
        f"{image.label}: unframed idle bytes changed parser state",
    )

    harness.machine.write8(image.symbols["_vdp_protocol_state"], 0xFF)
    recovery_steps = harness.feed(0x55)
    _require(
        harness.byte("_vdp_protocol_state") == 0,
        f"{image.label}: invalid parser state did not fail closed",
    )

    maximum_steps = max([recovery_steps, *idle_steps])
    for length in range(BUFFER_LENGTH + 1):
        harness = ProtocolHarness(image)
        maximum_steps = max(maximum_steps, harness.feed(0x8A), harness.feed(length))
        expected_header_state = 0 if length == 0 else 2
        _require(
            harness.byte("_vdp_protocol_state") == expected_header_state,
            f"{image.label}: legal length {length} entered the wrong state",
        )
        payload = bytes((index * 37 + length) & 0xFF for index in range(length))
        for index, value in enumerate(payload):
            maximum_steps = max(maximum_steps, harness.feed(value))
            remaining = length - index - 1
            _require(
                harness.byte("_vdp_protocol_len") == remaining,
                f"{image.label}: legal length {length} counter drifted at byte {index}",
            )
            _require(
                harness.byte("_vdp_protocol_state") == (0 if remaining == 0 else 2),
                f"{image.label}: legal length {length} ended at the wrong byte",
            )
        _require(
            harness.buffer()[:length] == payload,
            f"{image.label}: legal length {length} payload bytes changed",
        )
        _verify_general_poll(harness, f"{image.label}: after legal length {length}")

    _require(
        maximum_steps <= 128,
        f"{image.label}: linked parser exceeded the declared per-byte instruction budget",
    )


def reproduces_stale_length_bug(image: FirmwareImage) -> bool:
    """Return true only when the historical 17-byte discard consumes a later GP."""
    harness = ProtocolHarness(image)
    harness.feed_all([0x81, 17])
    if harness.byte("_vdp_protocol_state") != 3:
        return False
    if harness.byte("_vdp_protocol_len") == 17:
        return False
    harness.feed_all(bytes([0x55]) * 17)
    harness.feed_all([0x80, 1, 0xA5])
    return (
        harness.byte("_vdp_protocol_state") == 3
        and harness.byte("_gp") == 0x5A
        and harness.buffer() == bytes([harness.sentinel]) * BUFFER_LENGTH
    )


def verify_handshake_structure(image: FirmwareImage) -> None:
    """Prove that the linked banner remains downstream of the blocking GP poll."""
    symbols = image.symbols
    main = symbols["_main"]
    main_end = min(main + 0x800, len(image.rom))

    def call(target: int) -> bytes:
        return bytes([0xCD]) + target.to_bytes(3, "little")

    wait_calls = [
        match.start()
        for match in re.finditer(re.escape(call(symbols["_wait_ESP32"])), image.rom[main:main_end])
    ]
    banner_calls = [
        match.start()
        for match in re.finditer(re.escape(call(symbols["_bootmsg"])), image.rom[main:main_end])
    ]
    _require(len(wait_calls) == 1, f"{image.label}: _main lacks one VDP wait call")
    _require(len(banner_calls) == 1, f"{image.label}: _main lacks one banner call")
    _require(
        wait_calls[0] < banner_calls[0],
        f"{image.label}: MOS banner is no longer downstream of VDP wait",
    )

    wait_start = symbols["_wait_ESP32"]
    wait_end = symbols["_init_interrupts"]
    _require(wait_start < wait_end <= len(image.rom), f"{image.label}: bad wait bounds")
    wait_code = image.rom[wait_start:wait_end]
    gp = symbols["_gp"].to_bytes(3, "little")
    store_gp = wait_code.find(bytes([0x32]) + gp)
    load_pattern = bytes([0x3A]) + gp
    loads = [match.start() for match in re.finditer(re.escape(load_pattern), wait_code)]
    _require(store_gp >= 0, f"{image.label}: VDP wait does not initialize GP state")
    _require(len(loads) >= 2, f"{image.label}: VDP wait does not poll GP state")
    _require(store_gp < loads[0], f"{image.label}: GP poll precedes initialization")

    has_back_edge = False
    for offset in range(len(wait_code) - 1):
        if wait_code[offset] not in (0x18, 0x20, 0x28, 0x30, 0x38):
            continue
        displacement = wait_code[offset + 1]
        if displacement & 0x80:
            displacement -= 0x100
        target = offset + 2 + displacement
        if target <= loads[0] < offset:
            has_back_edge = True
            break
    _require(has_back_edge, f"{image.label}: GP poll has no backward wait edge")


def load_candidate(nm: Path, elf: Path, binary: Path) -> FirmwareImage:
    for path, label in ((nm, "nm"), (elf, "candidate ELF"), (binary, "candidate ROM")):
        _require(path.is_file(), f"missing {label}: {path}")
    _require(os.access(nm, os.X_OK), f"nm is not executable: {nm}")
    try:
        completed = subprocess.run(
            [os.fspath(nm), "-n", os.fspath(elf)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise VdpRegressionError(f"nm failed for candidate ELF: {error.stderr.strip()}") from error
    required = tuple(dict.fromkeys(PROTOCOL_SYMBOLS + HANDSHAKE_SYMBOLS))
    symbols = parse_nm_symbols(completed.stdout, required)
    return FirmwareImage("AgonDev candidate", binary.read_bytes(), symbols)


def load_zds_reference(binary: Path, linker_map: Path) -> FirmwareImage:
    _require(binary.is_file(), f"missing ZDS reference ROM: {binary}")
    _require(linker_map.is_file(), f"missing ZDS reference map: {linker_map}")
    rom = binary.read_bytes()
    map_bytes = linker_map.read_bytes()
    require_sha256("ZDS reference ROM", rom, ZDS_REFERENCE_BIN_SHA256)
    require_sha256("ZDS reference map", map_bytes, ZDS_REFERENCE_MAP_SHA256)
    symbols = parse_zds_map_symbols(
        map_bytes.decode("latin-1"),
        PROTOCOL_SYMBOLS,
    )
    return FirmwareImage("pinned pre-fix ZDS reference", rom, symbols)


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--nm",
        type=Path,
        default=root / "toolchains/agondev/bin/ez80-none-elf-nm",
    )
    parser.add_argument(
        "--candidate-elf",
        type=Path,
        default=root / "projects/mos-port/bin/MOS.elf",
    )
    parser.add_argument(
        "--candidate-bin",
        type=Path,
        default=root / "projects/mos-port/bin/MOS.bin",
    )
    parser.add_argument(
        "--reference-bin",
        type=Path,
        default=root / "emulator/firmware/mos_platform.bin",
    )
    parser.add_argument(
        "--reference-map",
        type=Path,
        default=root / "emulator/firmware/mos_platform.map",
    )
    parser.add_argument(
        "--check-reference-negative-control",
        action="store_true",
        help=(
            "also require the exact pinned ZDS reference to reproduce the "
            "historical stale-length defect"
        ),
    )
    args = parser.parse_args(argv)

    try:
        candidate = load_candidate(
            args.nm.expanduser().resolve(),
            args.candidate_elf.expanduser().resolve(),
            args.candidate_bin.expanduser().resolve(),
        )
        verify_handshake_structure(candidate)
        verify_framing_boundaries(candidate)
        verify_oversized_packets(candidate)

        if args.check_reference_negative_control:
            reference = load_zds_reference(
                args.reference_bin.expanduser().resolve(),
                args.reference_map.expanduser().resolve(),
            )
            _require(
                reproduces_stale_length_bug(reference),
                "pinned ZDS reference no longer reproduces the expected pre-fix bug; "
                "refresh the reference contract",
            )
    except (OSError, VdpRegressionError) as error:
        print(f"verify_vdp_regressions.py: {error}", file=os.sys.stderr)
        return 1

    print(
        "Linked VDP protocol verified: blocking GP wait precedes the banner; "
        "idle/recovery and lengths 0..16 frame exactly; all oversized lengths "
        "17..255 discard exactly and resume with GP"
    )
    if args.check_reference_negative_control:
        print(
            "Pinned ZDS image reproduced the historical stale-length defect as an "
            "intentional negative control"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
