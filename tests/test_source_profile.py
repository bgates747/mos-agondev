from __future__ import annotations

from pathlib import Path
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
        runtime_audit = (
            ROOT / "projects/mos-port/runtime/audit_runtime.py"
        ).read_text(encoding="utf-8")
        start_here = (ROOT / "STARTHERE.md").read_text(encoding="utf-8")
        for name in (
            "SOURCE_PROFILE",
            "C_SOURCES_EXTRA",
            "C_OBJECT_RELATIVE_EXTRA",
            "CPPFLAGS_EXTRA",
            "PARITY_EXPECTED_COMMANDS",
            "FIRMWARE_LINK_CHECKS",
        ):
            self.assertIn(name, root_make)
        self.assertIn("$(C_SOURCES_EXTRA)", port_make)
        self.assertIn("$(CPPFLAGS_EXTRA)", port_make)
        self.assertIn("$(C_OBJECT_RELATIVE_EXTRA)", runtime_make)
        self.assertIn('ASSEMBLY_SOURCE="$(MOS_WORKTREE)"', root_make)
        self.assertIn('--assembly "$(ASSEMBLY_SOURCE)"', runtime_make)
        self.assertIn("$(sort $(C_SOURCES_BASE) $(C_SOURCES_EXTRA))", port_make)
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
        self.assertNotIn("src/emos.c", root_make + port_make + runtime_make)


if __name__ == "__main__":
    unittest.main()
