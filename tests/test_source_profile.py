from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SourceProfileTests(unittest.TestCase):
    def test_profile_surface_is_explicit_and_product_neutral(self) -> None:
        root_make = (ROOT / "Makefile").read_text(encoding="utf-8")
        port_make = (ROOT / "projects/mos-port/Makefile").read_text(
            encoding="utf-8"
        )
        runtime_make = (ROOT / "projects/mos-port/runtime/Makefile").read_text(
            encoding="utf-8"
        )
        assembly_profile = (
            ROOT / "projects/mos-port/assembly-profile.mk"
        ).read_text(encoding="utf-8")
        assembly_validator = (
            ROOT / "projects/mos-port/tools/profile_assembly.py"
        ).read_text(encoding="utf-8")
        runtime_audit = (
            ROOT / "projects/mos-port/runtime/audit_runtime.py"
        ).read_text(encoding="utf-8")
        start_here = (ROOT / "STARTHERE.md").read_text(encoding="utf-8")
        for name in (
            "SOURCE_PROFILE",
            "C_SOURCES_EXTRA",
            "C_OBJECT_RELATIVE_EXTRA",
            "ASM_SOURCES_EXTRA",
            "ASM_OBJECT_RELATIVE_EXTRA",
            "CPPFLAGS_EXTRA",
            "PARITY_EXPECTED_COMMANDS",
            "FIRMWARE_LINK_CHECKS",
        ):
            self.assertIn(name, root_make)
        self.assertIn("$(C_SOURCES_EXTRA)", port_make)
        self.assertIn("$(ASM_SOURCES)", port_make)
        self.assertIn("$(ASM_OBJECT_RELATIVE)", port_make)
        self.assertIn("$(CPPFLAGS_EXTRA)", port_make)
        self.assertIn("$(C_OBJECT_RELATIVE_EXTRA)", runtime_make)
        self.assertIn('ASSEMBLY_SOURCE="$(MOS_WORKTREE)"', root_make)
        self.assertIn('ASM_SOURCES_EXTRA="$(ASM_SOURCES_EXTRA)"', root_make)
        self.assertIn('--assembly "$(ASSEMBLY_SOURCE)"', runtime_make)
        self.assertIn("$(sort $(C_SOURCES_BASE) $(C_SOURCES_EXTRA))", port_make)
        self.assertIn(
            "ASM_SOURCES := $(ASM_SOURCES_BASE) $(sort $(ASM_SOURCES_EXTRA))",
            assembly_profile,
        )
        self.assertIn(
            "ASM_OBJECT_RELATIVE := $(ASM_OBJECT_RELATIVE_BASE)", assembly_profile
        )
        self.assertIn(
            "ASM_OBJECT_RELATIVE_EXTRA must exactly match ASM_SOURCES_EXTRA",
            assembly_profile,
        )
        self.assertIn("ASM_SOURCES_DECLARED", port_make + assembly_profile)
        self.assertIn("ASM_OBJECT_RELATIVE_DECLARED", port_make + assembly_profile)
        self.assertIn("profile-assembly-check", port_make)
        self.assertIn("validate_assembly_composition", assembly_validator)
        self.assertIn("$(MAKE) profile-linked-check", root_make)
        self.assertIn("for checker in $(FIRMWARE_LINK_CHECKS)", root_make)
        for argument in ("--source", "--elf", "--nm", "--objdump"):
            self.assertIn(argument, root_make)
        self.assertIn(
            "$(sort $(C_OBJECT_RELATIVE_BASE) $(C_OBJECT_RELATIVE_EXTRA))",
            runtime_make,
        )
        self.assertIn("--c-object", runtime_make)
        self.assertIn("extra_c_objects", runtime_audit)
        self.assertIn("`CPPFLAGS_EXTRA`", start_here)
        generic_build = root_make + port_make + runtime_make + assembly_profile
        self.assertNotIn("src/emos.c", generic_build)
        self.assertNotIn("emos_parallel", generic_build + assembly_validator)

    def test_empty_assembly_profile_preserves_upstream_order(self) -> None:
        port_make = ROOT / "projects" / "mos-port" / "Makefile"
        command = [
            "make",
            "--no-print-directory",
            "-f",
            str(port_make),
            "-pn",
        ]
        completed = subprocess.run(
            command,
            cwd=port_make.parent,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        variables = {}
        for line in completed.stdout.splitlines():
            if line.startswith("ASM_SOURCES_BASE := "):
                variables["base"] = line.removeprefix("ASM_SOURCES_BASE := ").split()
            elif line.startswith("ASM_SOURCES := "):
                variables["selected"] = line.removeprefix("ASM_SOURCES := ").split()
        self.assertEqual(variables["selected"], variables["base"])

    def test_make_preflight_observes_unsorted_duplicate_declarations(self) -> None:
        port = ROOT / "projects" / "mos-port"
        completed = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-C",
                str(port),
                f"UPSTREAM={port / 'worktree'}",
                "ASM_SOURCES_EXTRA=src/serial.asm src/serial.asm",
                "ASM_OBJECT_RELATIVE_EXTRA=src/serial.o src/serial.o",
                "profile-assembly-check",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("duplicate configured assembly source", completed.stderr)


if __name__ == "__main__":
    unittest.main()
