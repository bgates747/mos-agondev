from __future__ import annotations

import importlib.util
import sys
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path


PORT_ROOT = Path(__file__).resolve().parents[1] / "projects/mos-port"
sys.path.insert(0, str(PORT_ROOT))
SPEC = importlib.util.spec_from_file_location("compare_boot", PORT_ROOT / "compare_boot.py")
assert SPEC and SPEC.loader
compare_boot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare_boot)


class CompareBootTests(unittest.TestCase):
    def test_command_set_is_read_only_or_process_local(self) -> None:
        commands = compare_boot.COMMANDS.decode("ascii").splitlines()
        self.assertIn("set PortTest a value with spaces", commands)
        self.assertIn("unset PortTest", commands)
        self.assertIn("cd nested", commands)
        self.assertIn("type nested/deeper/final.txt", commands)
        self.assertIn("cd /", commands)
        for destructive in ("save", "delete", "erase", "mkdir", "copy", "move"):
            self.assertFalse(
                any(command.casefold().startswith(destructive) for command in commands)
            )

    def test_creates_exact_curated_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            compare_boot.create_fixture(root)
            actual = {
                str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual, compare_boot.FIXTURE_FILES)
            compare_boot.validate_fixture(root)
            (root / "nested/inner.txt").write_bytes(b"changed")
            with self.assertRaisesRegex(compare_boot.ParityError, "content changed"):
                compare_boot.validate_fixture(root)
            with self.assertRaisesRegex(compare_boot.ParityError, "not empty"):
                compare_boot.create_fixture(root)

    def test_normalizes_transport_noise(self) -> None:
        output = (
            b"Tom's Fake VDP Version 1.03\nunknown packet VDU 0x17\n"
            b"\x80Agon Platform MOS Version 3.0.2 Arthur\r\n\r\n"
            b"/ *time\r\nSun, 00/01/1980 00:00:00\r\n/ *"
        )
        self.assertEqual(
            compare_boot.normalize(output),
            [
                "Agon Platform MOS Version 3.0.2 Arthur",
                "/ *time",
                "Sun, 00/01/1980 00:00:00",
                "/ *",
            ],
        )

    def test_reports_stable_difference(self) -> None:
        reference = b"Agon Platform MOS Version 3.0.2 Arthur\n/ *credits\nFatFS\n"
        candidate = b"Agon Platform MOS Version 3.0.2 Arthur\n/ *credits\nOther\n"
        with self.assertRaisesRegex(compare_boot.ParityError, "FatFS"):
            compare_boot.compare(candidate, reference)

    def test_rejects_matching_but_incomplete_transcripts(self) -> None:
        output = b"Agon Platform MOS Version 3.0.2 Arthur\n/ *\n"
        with self.assertRaisesRegex(compare_boot.ParityError, "lack required"):
            compare_boot.compare(output, output)

    def test_requires_every_command_echo_and_unset_state(self) -> None:
        output = b"Agon Platform MOS Version 3.0.2 Arthur\n/ *one\n"
        with mock.patch.object(compare_boot, "REQUIRED_TRANSCRIPT_TOKENS", ()), \
             mock.patch.object(compare_boot, "COMMANDS", b"one\ntwo\n"):
            with self.assertRaisesRegex(compare_boot.ParityError, "did not execute.*two"):
                compare_boot.compare(output, output)

        state = (
            b"Agon Platform MOS Version 3.0.2 Arthur\n"
            b"/ *set PortTest a value with spaces\n"
            b"/ *show PortTest\na value with spaces\n"
            b"/ *unset PortTest\n/ *show PortTest\na value with spaces\n"
        )
        with mock.patch.object(compare_boot, "REQUIRED_TRANSCRIPT_TOKENS", ()), \
             mock.patch.object(
                 compare_boot,
                 "COMMANDS",
                 b"set PortTest a value with spaces\nshow PortTest\n"
                 b"unset PortTest\nshow PortTest\n",
             ):
            with self.assertRaisesRegex(compare_boot.ParityError, "UNSET state"):
                compare_boot.compare(state, state)

    def test_reports_timeout_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = root / "fab-cli"
            firmware = root / "MOS.bin"
            sdcard = root / "sd"
            cli.write_bytes(b"stub")
            cli.chmod(0o755)
            firmware.write_bytes(b"rom")
            sdcard.mkdir()
            with mock.patch.object(
                compare_boot.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired([str(cli)], 0.25, output=b"partial"),
            ):
                with self.assertRaisesRegex(compare_boot.ParityError, "exceeded 0.25"):
                    compare_boot.run(cli, firmware, sdcard, 0.25)

    def test_reports_nonzero_and_empty_emulator_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cli = root / "fab-cli"
            firmware = root / "MOS.bin"
            sdcard = root / "sd"
            cli.write_bytes(b"stub")
            cli.chmod(0o755)
            firmware.write_bytes(b"rom")
            sdcard.mkdir()
            with mock.patch.object(
                compare_boot.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 3, b"failure"),
            ):
                with self.assertRaisesRegex(compare_boot.ParityError, "exited 3"):
                    compare_boot.run(cli, firmware, sdcard, 1.0)
            with mock.patch.object(
                compare_boot.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, b""),
            ):
                with self.assertRaisesRegex(compare_boot.ParityError, "no output"):
                    compare_boot.run(cli, firmware, sdcard, 1.0)
            with mock.patch.object(
                compare_boot.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    [], 0, b"x" * (compare_boot.MAX_OUTPUT_BYTES + 1)
                ),
            ):
                with self.assertRaisesRegex(compare_boot.ParityError, "output exceeded"):
                    compare_boot.run(cli, firmware, sdcard, 1.0)


if __name__ == "__main__":
    unittest.main()
