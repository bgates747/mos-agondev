from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "projects/contract-probe/verify_contract.py"
)
SPEC = importlib.util.spec_from_file_location("verify_contract", SCRIPT)
assert SPEC and SPEC.loader
verify_contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_contract)


class ContractProbeTests(unittest.TestCase):
    def test_finds_root_and_release_cli_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root_cli = root / "agon-cli-emulator"
            root_cli.write_bytes(b"stub")
            root_cli.chmod(0o755)
            self.assertEqual(verify_contract.find_cli(root), root_cli)

            root_cli.unlink()
            release_cli = root / "target/release/agon-cli-emulator"
            release_cli.parent.mkdir(parents=True)
            release_cli.write_bytes(b"stub")
            release_cli.chmod(0o755)
            self.assertEqual(verify_contract.find_cli(root), release_cli)

    def test_rejects_missing_cli_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(verify_contract.ContractError, "missing"):
                verify_contract.find_cli(Path(temporary))

    def test_extracts_only_the_stable_contract_block(self) -> None:
        output = (
            b"transport noise\nCONTRACT-BEGIN\nFORMAT-PRINTF\n"
            b"CONTRACT-PASS\n/ *"
        )
        self.assertEqual(
            verify_contract.validate_output(output, Path("candidate.bin")),
            b"CONTRACT-BEGIN\nFORMAT-PRINTF\nCONTRACT-PASS\n",
        )

    def test_rejects_failure_even_if_pass_marker_is_present(self) -> None:
        output = (
            b"CONTRACT-BEGIN\nFORMAT-PRINTF\nCONTRACT-FAIL api\n"
            b"CONTRACT-PASS\n"
        )
        with self.assertRaisesRegex(verify_contract.ContractError, "reported failure"):
            verify_contract.validate_output(output, Path("candidate.bin"))

    def test_rejects_truncated_output(self) -> None:
        with self.assertRaisesRegex(verify_contract.ContractError, "CONTRACT-PASS"):
            verify_contract.validate_output(
                b"CONTRACT-BEGIN\nFORMAT-PRINTF\n", Path("candidate.bin")
            )

    def test_rejects_markers_out_of_order(self) -> None:
        output = (
            b"CONTRACT-PASS\nCONTRACT-BEGIN\nFORMAT-PRINTF\n"
        )
        with self.assertRaisesRegex(verify_contract.ContractError, "ordered"):
            verify_contract.validate_output(output, Path("candidate.bin"))

    def test_rejects_formatter_marker_before_contract_block(self) -> None:
        output = b"FORMAT-PRINTF\nCONTRACT-BEGIN\nCONTRACT-PASS\n"
        with self.assertRaisesRegex(verify_contract.ContractError, "ordered"):
            verify_contract.validate_output(output, Path("candidate.bin"))

    def test_fixture_snapshot_detects_content_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture.bin"
            fixture.write_bytes(b"before")
            before = verify_contract.fixture_snapshot(root)
            fixture.write_bytes(b"after")
            self.assertNotEqual(verify_contract.fixture_snapshot(root), before)

    def test_rejects_nonpositive_timeout_without_launching(self) -> None:
        with self.assertRaisesRegex(verify_contract.ContractError, "positive"):
            verify_contract.run(
                Path("missing-cli"),
                Path("missing-firmware"),
                Path("missing-sdcard"),
                0,
            )

    def test_target_formatter_markers_match_current_mos_inventory(self) -> None:
        project = SCRIPT.parents[2]
        verify_contract.verify_target_format_coverage(project)


if __name__ == "__main__":
    unittest.main()
