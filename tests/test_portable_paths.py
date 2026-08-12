from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PortablePathTests(unittest.TestCase):
    def test_tracked_text_has_no_machine_specific_paths(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        )
        forbidden = re.compile(
            "|".join(
                (
                    "/" + "home/",
                    "/" + "Users/",
                    "/" + "tmp/",
                    "~" + "/",
                    r"\$\{?" + "HOME" + r"\}?",
                    "Path." + "home" + r"\(",
                    r"\b[A-Za-z]:\\" + "Users" + r"\\",
                )
            )
        )
        workspace_layout = re.compile(
            r"(?:\.\./){2,}(?:agondev|agon-mos|agon-docs|agon-vdp|"
            r"agondev-tests|fab-agon-emulator)(?:/|\b)"
        )
        violations: list[str] = []
        for raw_name in result.stdout.split(b"\0"):
            if not raw_name:
                continue
            relative = Path(raw_name.decode("utf-8"))
            path = ROOT / relative
            try:
                text = path.read_text(encoding="utf-8")
            except (FileNotFoundError, UnicodeDecodeError, IsADirectoryError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                layout_violation = (
                    not relative.parts or relative.parts[0] != "research"
                ) and workspace_layout.search(line)
                if forbidden.search(line) or layout_violation:
                    violations.append(f"{relative}:{line_number}: {line.strip()}")
        self.assertEqual([], violations, "machine-specific paths found")

    def test_make_normalizes_relative_fab_root_before_recursive_builds(self) -> None:
        supplied = Path("../portable-fab-fixture")
        expected = (ROOT / supplied).resolve()
        result = subprocess.run(
            ["make", "-n", f"FAB_ROOT={supplied}", "contract-check"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'FAB_ROOT="{expected}" clean', result.stdout)
        self.assertIn(f'FAB_ROOT="{expected}" verify', result.stdout)
        self.assertNotIn(f'FAB_ROOT="{supplied}"', result.stdout)

    def test_frozen_vdp_reference_is_only_in_the_baseline_gate(self) -> None:
        current = subprocess.run(
            ["make", "-n", "vdp-regression-check"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertNotIn("--check-reference-negative-control", current.stdout)

        baseline = subprocess.run(
            ["make", "-n", "vdp-baseline-check"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        self.assertIn("--check-reference-negative-control", baseline.stdout)

    def test_firmware_builds_run_provenance_before_compilation(self) -> None:
        root_dry_run = subprocess.run(
            ["make", "-n", "firmware-check"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(root_dry_run.returncode, 0, root_dry_run.stderr)
        self.assertIn("prepare_mos_worktree.py --check", root_dry_run.stdout)

        direct = subprocess.run(
            [
                "make",
                "-Bn",
                "-C",
                "projects/mos-port",
                f"TOOLCHAIN={ROOT / 'toolchains/agondev'}",
                f"UPSTREAM={ROOT / 'projects/mos-port/worktree'}",
                "c-objects",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(direct.returncode, 0, direct.stderr)
        provenance = direct.stdout.index("zds2gas.py provenance")
        compilation = direct.stdout.index("ez80-none-elf-clang")
        self.assertLess(provenance, compilation)


if __name__ == "__main__":
    unittest.main()
