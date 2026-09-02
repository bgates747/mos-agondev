from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "projects" / "mos-port"


class MakeProvenanceTests(unittest.TestCase):
    def _dry_recipe(self, directory: Path, target: str, provenance: bool) -> str:
        command = [
            "make",
            "--no-print-directory",
            "-Bn",
            "-C",
            str(directory),
        ]
        if provenance:
            command.append(f"PROVENANCE_DIR={ROOT / '.test-provenance-dry'}")
        command.append(target)
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        syntax = subprocess.run(
            ["sh", "-n"],
            input=completed.stdout,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        return completed.stdout

    def test_makefiles_cover_target_steps_and_final_link(self) -> None:
        root_make = (ROOT / "Makefile").read_text(encoding="utf-8")
        port_make = (PORT / "Makefile").read_text(encoding="utf-8")
        runtime_make = (PORT / "runtime" / "Makefile").read_text(encoding="utf-8")
        recorder = (PORT / "tools" / "record_target_step.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("provenance-start", root_make)
        self.assertIn("--initialize", root_make)
        self.assertIn('PROVENANCE_DIR="$(PROVENANCE_DIR_ABS)"', root_make)
        self.assertIn('PYTHON_ENV="$(PYTHON_ENV)"', root_make)
        for kind in (
            "c-compile",
            "c-assembly",
            "wrapped-assembly",
            "direct-assembly",
            "final-link",
        ):
            self.assertIn(f"--kind {kind}", port_make)
        self.assertIn("--dependency-file bin/MOS.link.d --trace", port_make)
        self.assertIn("--stdout-file \"bin/MOS.link.trace\"", port_make)
        self.assertIn("$(C_PRODUCER_ARGS)", port_make)
        self.assertIn("$(ASM_PRODUCER_ARGS)", port_make)
        self.assertIn("$(ZDS2GAS)", port_make)
        self.assertIn('--nested-executable "$(AS)"', port_make)
        self.assertIn('--driver-selected-executable "$(AS)"', port_make)
        self.assertIn("-fno-integrated-as -B$(TOOLBIN)", port_make)
        self.assertIn('ASSEMBLY_SOURCE="$(UPSTREAM)"', port_make)
        self.assertIn('--root "PYTHON_ENV=$(abspath $(PYTHON_ENV))"', port_make)
        self.assertIn("--kind c-compile", runtime_make)
        self.assertIn("--kind direct-assembly", runtime_make)
        self.assertIn('--nested-executable "$(EZ80_AS)"', runtime_make)
        self.assertIn(
            '--driver-selected-executable "$(EZ80_AS)"', runtime_make
        )
        self.assertIn("-fno-integrated-as -B$(TOOLCHAIN)/bin", runtime_make)
        self.assertIn(
            '--root "PYTHON_ENV=$(abspath $(PYTHON_ENV))"', runtime_make
        )
        self.assertIn('Path(__file__), cwd, roots, "provenance recorder"', recorder)
        self.assertIn('"response_files":', recorder)
        self.assertIn('"environment": environment_record()', recorder)
        self.assertIn('"driver_selection": driver_selection', recorder)

    def test_empty_and_enabled_recipes_are_shell_syntax_valid(self) -> None:
        cases = (
            (PORT, "obj/main.o"),
            (PORT, "obj/asm/src_startup/cstartup.o"),
            (PORT, "obj/hostfs_descriptor.o"),
            (
                PORT / "runtime",
                str(PORT / "runtime" / "build" / "firmware_printf.o"),
            ),
            (
                PORT / "runtime",
                str(PORT / "runtime" / "build" / "i48_required.o"),
            ),
        )
        for directory, target in cases:
            with self.subTest(directory=directory, target=target, provenance=False):
                output = self._dry_recipe(directory, target, provenance=False)
                self.assertIn('if test -n ""; then', output)
            with self.subTest(directory=directory, target=target, provenance=True):
                output = self._dry_recipe(directory, target, provenance=True)
                self.assertIn("record_target_step.py", output)


if __name__ == "__main__":
    unittest.main()
