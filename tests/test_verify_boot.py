from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "projects/mos-port/verify_boot.py"
SPEC = importlib.util.spec_from_file_location("verify_boot", SCRIPT)
assert SPEC and SPEC.loader
verify_boot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_boot)


class VerifyBootTests(unittest.TestCase):
    def test_accepts_shell_and_hostfs_evidence(self) -> None:
        verify_boot.validate_output(
            b"Agon Platform MOS Version 3.0.2\n"
            b"Volume: hostfs\nDirectory: /\nagondev bin\n"
        )

    def test_rejects_absent_sdcard_even_with_banner(self) -> None:
        with self.assertRaisesRegex(verify_boot.BootError, "No SD card present"):
            verify_boot.validate_output(
                b"Agon Platform MOS Version 3.0.2\nNo SD card present\n"
            )

    def test_finds_only_an_executable_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "target/release/agon-cli-emulator"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"#!/bin/sh\n")
            with self.assertRaises(verify_boot.BootError):
                verify_boot.find_cli(root)
            candidate.chmod(0o755)
            self.assertEqual(verify_boot.find_cli(root), candidate)


if __name__ == "__main__":
    unittest.main()
