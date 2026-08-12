from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_source.py"
SPEC = importlib.util.spec_from_file_location("audit_source", SCRIPT)
assert SPEC and SPEC.loader
audit_source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_source)


class AuditSourceTests(unittest.TestCase):
    def test_parses_zds_space_rows(self) -> None:
        sample = """
RAM D:0BC000 D:0BCBD4 4000H BD5H 342BH
ROM C:000000 C:01A7C9 20000H 1A735H 58CBH
"""
        spaces = audit_source.parse_zds_space_allocation(sample)
        self.assertEqual(spaces["ram"]["capacity_bytes"], 16384)
        self.assertEqual(spaces["ram"]["used_bytes"], 3029)
        self.assertEqual(spaces["rom"]["capacity_bytes"], 131072)
        self.assertEqual(spaces["rom"]["used_bytes"], 108341)

    def test_counts_relevant_zds_constructs(self) -> None:
        source = """
DEFINE RESET, SPACE = ROM
SEGMENT RESET
VALUE: MACRO ARG
  DB %FF
  JR $F
$$:
  LD DE,HL
  DL 00000001b
SCOPE
"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.asm"
            path.write_text(source, encoding="utf-8")
            counts = audit_source.assembly_construct_counts([path])
        self.assertEqual(counts["percent_hex_literals"], 1)
        self.assertEqual(counts["forward_backward_local_refs"], 1)
        self.assertEqual(counts["dollar_dollar_local_definitions"], 1)
        self.assertEqual(counts["binary_suffix_literals"], 1)
        self.assertEqual(counts["dl_or_dw24_directives"], 1)
        self.assertEqual(counts["zds_macro_definitions"], 1)
        self.assertEqual(counts["wide_register_copy_pseudo_ops"], 1)


if __name__ == "__main__":
    unittest.main()
