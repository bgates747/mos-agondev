from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "projects/mos-port/verify_vdp_regressions.py"
SPEC = importlib.util.spec_from_file_location("verify_vdp_regressions", SCRIPT)
assert SPEC and SPEC.loader
vdp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vdp)


# First 183 bytes of the assembled protocol unit, through the GP handler.  The
# fixture patches its relocations to synthetic ROM/RAM addresses below.
PROTOCOL_BYTES = bytes.fromhex(
    "3a000000b728113d28213d283c3dca9e0000af32000000c979d680d832000000"
    "220000003e0132000000c979fe11380b320000003e0332000000c932000000b7"
    "281b3e0232000000c92a0000007123220000003a0000003d32000000c0af3200"
    "00003a000000fe0ad011760000210000006f292919e9c3ae0000c3b70000c301"
    "0100c31c0100c32f0100c34a0100c3650100c3b00100c3c90100c3d801003a"
    "0000003d32000000c0af32000000c93a00000032000000c9"
)


def protocol_fixture(*, stale_length_bug: bool = False) -> vdp.FirmwareImage:
    base = 0x20
    rom = bytearray(0x300)
    rom[base : base + len(PROTOCOL_BYTES)] = PROTOCOL_BYTES
    symbols = {
        "vdp_protocol": base,
        "_vdp_protocol_state": 0x1000,
        "_vdp_protocol_cmd": 0x1001,
        "_vdp_protocol_len": 0x1002,
        "_vdp_protocol_ptr": 0x1003,
        "_vdp_protocol_data": 0x1010,
        "_gp": 0x1020,
    }

    def patch24(operand_offset: int, value: int) -> None:
        rom[base + operand_offset : base + operand_offset + 3] = value.to_bytes(3, "little")

    external_relocations = {
        0x01: "_vdp_protocol_state",
        0x14: "_vdp_protocol_state",
        0x1D: "_vdp_protocol_cmd",
        0x21: "_vdp_protocol_ptr",
        0x27: "_vdp_protocol_state",
        0x31: "_vdp_protocol_len",
        0x37: "_vdp_protocol_state",
        0x3C: "_vdp_protocol_len",
        0x45: "_vdp_protocol_state",
        0x4A: "_vdp_protocol_ptr",
        0x50: "_vdp_protocol_ptr",
        0x54: "_vdp_protocol_len",
        0x59: "_vdp_protocol_len",
        0x5F: "_vdp_protocol_state",
        0x63: "_vdp_protocol_cmd",
        0x9F: "_vdp_protocol_len",
        0xA4: "_vdp_protocol_len",
        0xAA: "_vdp_protocol_state",
        0xAF: "_vdp_protocol_data",
        0xB3: "_gp",
    }
    for operand_offset, name in external_relocations.items():
        patch24(operand_offset, symbols[name])

    local_relocations = {
        0x0F: 0x9E,
        0x6A: 0x76,
        0x77: 0xAE,
        0x7B: 0xB7,
        0x7F: 0x101,
        0x83: 0x11C,
        0x87: 0x12F,
        0x8B: 0x14A,
        0x8F: 0x165,
        0x93: 0x1B0,
        0x97: 0x1C9,
        0x9B: 0x1D8,
    }
    for operand_offset, target_offset in local_relocations.items():
        patch24(operand_offset, base + target_offset)

    if stale_length_bug:
        # Model the historical branch by removing only its length store while
        # retaining all later linked addresses.
        rom[base + 0x30 : base + 0x34] = bytes([0x79, 0xB7, 0xB7, 0xB7])
    return vdp.FirmwareImage("synthetic protocol", bytes(rom), symbols)


def handshake_fixture(*, banner_first: bool = False) -> vdp.FirmwareImage:
    rom = bytearray(0x300)
    gp = 0x1000
    wait = 0x40
    init = 0x60
    boot = 0x70
    main = 0x80
    gp_bytes = gp.to_bytes(3, "little")
    wait_code = (
        bytes([0x32]) + gp_bytes
        + bytes([0x3A]) + gp_bytes
        + bytes([0xB7, 0x20, 0x07])
        + bytes([0x3A]) + gp_bytes
        + bytes([0xB7, 0x28, 0xF2, 0xC9])
    )
    rom[wait : wait + len(wait_code)] = wait_code
    calls = (boot, wait) if banner_first else (wait, boot)
    main_code = b"".join(bytes([0xCD]) + target.to_bytes(3, "little") for target in calls)
    rom[main : main + len(main_code)] = main_code
    return vdp.FirmwareImage(
        "synthetic handshake",
        bytes(rom),
        {
            "_main": main,
            "_wait_ESP32": wait,
            "_init_interrupts": init,
            "_bootmsg": boot,
            "_gp": gp,
        },
    )


class VdpRegressionTests(unittest.TestCase):
    def test_executes_all_oversized_lengths_and_legal_boundary(self) -> None:
        vdp.verify_oversized_packets(protocol_fixture())

    def test_stale_length_negative_control_is_behavioral(self) -> None:
        self.assertFalse(vdp.reproduces_stale_length_bug(protocol_fixture()))
        buggy = protocol_fixture(stale_length_bug=True)
        self.assertTrue(vdp.reproduces_stale_length_bug(buggy))
        with self.assertRaisesRegex(vdp.VdpRegressionError, "was not preserved"):
            vdp.verify_oversized_packets(buggy)

    def test_rejects_an_opcode_outside_the_bounded_interpreter(self) -> None:
        image = vdp.FirmwareImage("unknown opcode", bytes([0xFF]), {"vdp_protocol": 0})
        with self.assertRaisesRegex(vdp.VdpRegressionError, "unsupported opcode 0xff"):
            vdp.Ez80ProtocolMachine(image).call_protocol(0, 0x1000)

    def test_parses_candidate_and_zds_symbols_strictly(self) -> None:
        nm = "0000002b t state\n00000010 T wanted\n"
        self.assertEqual(vdp.parse_nm_symbols(nm, ("wanted",)), {"wanted": 0x10})
        with self.assertRaisesRegex(vdp.VdpRegressionError, "lacks symbols"):
            vdp.parse_nm_symbols(nm, ("absent",))

        zds_map = "wanted                            C:0011CA module .STARTUP\n"
        self.assertEqual(
            vdp.parse_zds_map_symbols(zds_map, ("wanted",)),
            {"wanted": 0x11CA},
        )

    def test_rejects_reference_hash_mismatch(self) -> None:
        payload = b"audited reference fixture"
        expected = hashlib.sha256(payload).hexdigest()
        vdp.require_sha256("test reference", payload, expected)
        with self.assertRaisesRegex(
            vdp.VdpRegressionError,
            r"test reference SHA-256 mismatch: expected [0-9a-f]{64}, got [0-9a-f]{64}",
        ):
            vdp.require_sha256("test reference", payload + b"!", expected)

    def test_handshake_requires_wait_before_banner_and_gp_back_edge(self) -> None:
        vdp.verify_handshake_structure(handshake_fixture())
        with self.assertRaisesRegex(vdp.VdpRegressionError, "downstream"):
            vdp.verify_handshake_structure(handshake_fixture(banner_first=True))

    def test_default_cli_checks_only_the_candidate(self) -> None:
        candidate = vdp.FirmwareImage("candidate", b"", {})
        stdout = io.StringIO()
        with mock.patch.object(vdp, "load_candidate", return_value=candidate), \
             mock.patch.object(vdp, "verify_handshake_structure") as handshake, \
             mock.patch.object(vdp, "verify_oversized_packets") as oversized, \
             mock.patch.object(vdp, "load_zds_reference") as load_reference, \
             contextlib.redirect_stdout(stdout):
            status = vdp.main(
                [
                    "--nm", "candidate-nm",
                    "--candidate-elf", "candidate.elf",
                    "--candidate-bin", "candidate.bin",
                ]
            )

        self.assertEqual(status, 0)
        handshake.assert_called_once_with(candidate)
        oversized.assert_called_once_with(candidate)
        load_reference.assert_not_called()
        self.assertNotIn("Pinned ZDS image", stdout.getvalue())

    def test_reference_negative_control_is_explicit(self) -> None:
        candidate = vdp.FirmwareImage("candidate", b"", {})
        reference = vdp.FirmwareImage("reference", b"", {})
        stdout = io.StringIO()
        with mock.patch.object(vdp, "load_candidate", return_value=candidate), \
             mock.patch.object(vdp, "verify_handshake_structure"), \
             mock.patch.object(vdp, "verify_oversized_packets"), \
             mock.patch.object(
                 vdp, "load_zds_reference", return_value=reference
             ) as load_reference, \
             mock.patch.object(
                 vdp, "reproduces_stale_length_bug", return_value=True
             ) as reproduces_bug, \
             contextlib.redirect_stdout(stdout):
            status = vdp.main(
                [
                    "--nm", "candidate-nm",
                    "--candidate-elf", "candidate.elf",
                    "--candidate-bin", "candidate.bin",
                    "--reference-bin", "reference.bin",
                    "--reference-map", "reference.map",
                    "--check-reference-negative-control",
                ]
            )

        self.assertEqual(status, 0)
        load_reference.assert_called_once()
        reproduces_bug.assert_called_once_with(reference)
        self.assertIn("Pinned ZDS image", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
