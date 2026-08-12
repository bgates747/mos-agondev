from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_probe_outputs.py"
SPEC = importlib.util.spec_from_file_location("verify_probe_outputs", SCRIPT)
assert SPEC and SPEC.loader
verify_probe_outputs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_probe_outputs)


class VerifyProbeOutputTests(unittest.TestCase):
    def test_parses_objdump_section_layout(self) -> None:
        output = """
Idx Name          Size      VMA       LMA       File off  Algn
  0 .reset        00000009  00000000  00000000  00010000  2**0
  1 .data         00000001  000bc000  00000262  0001c000  2**0
"""
        self.assertEqual(
            verify_probe_outputs.parse_objdump_sections(output),
            {".reset": (9, 0, 0), ".data": (1, 0x0BC000, 0x262)},
        )

    def test_aggregates_only_load_and_bss_sections(self) -> None:
        output = """
one.o  :
.text      100 0
.rodata     10 0
.comment   119 0
two.o  :
.text       20 0
.data        3 0
.bss         4 0
"""
        self.assertEqual(
            verify_probe_outputs.parse_size_totals(output),
            {".text": 120, ".rodata": 10, ".data": 3, ".bss": 4},
        )


if __name__ == "__main__":
    unittest.main()
