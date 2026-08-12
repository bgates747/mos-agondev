from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


AUDIT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AUDIT_ROOT))

from audit_wrappers import inventory  # noqa: E402


class WrapperAuditTests(unittest.TestCase):
    def test_inventory_classifies_stack_accesses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "aligned.src").write_text(
                "push ix\nld ix,0\nadd ix,sp\nld e,(ix+6)\nld hl,(ix+9)\n"
                "rst.lil 08h\n",
                encoding="utf-8",
            )
            (root / "mixed.src").write_text(
                "push ix\nld ix,0\nadd ix,sp\nld e,(ix+6)\nld hl,(ix+7)\n",
                encoding="utf-8",
            )
            (root / "unframed.src").write_text(
                "pop de\nex (sp),hl\npush de\nld hl,(ix+6)\n",
                encoding="utf-8",
            )
            (root / "pointer.src").write_text(
                "ld hl,9\nadd hl,sp\nld a,mos_getfunction\n",
                encoding="utf-8",
            )
            result = inventory(root)
            self.assertEqual(result.sources, 4)
            self.assertEqual(result.framed, 2)
            self.assertEqual(result.stack_exchange, 1)
            self.assertEqual(result.delegated, 1)
            self.assertEqual(result.direct_rst, 1)
            self.assertEqual(result.ix_operands, 5)
            self.assertEqual(result.unaligned, frozenset({("mixed.src", 7)}))
            self.assertEqual(result.unframed_ix, frozenset({"unframed.src"}))
            self.assertEqual(result.sp_derived, (("pointer.src", 9),))

    def test_current_pinned_inventory_has_three_known_defect_shapes(self) -> None:
        repository = AUDIT_ROOT.parents[1]
        release = (repository / "toolchains/agondev").resolve()
        result = inventory(release.parent / "src/lib/libmos")
        self.assertEqual(
            result.unaligned,
            frozenset({("mos_getError.src", 7), ("mos_getError.src", 10)}),
        )
        self.assertEqual(result.unframed_ix, frozenset({"ffs_setlabel.src"}))
        self.assertEqual(dict(result.sp_derived), {"mos_flseek_p.src": 9})


if __name__ == "__main__":
    unittest.main()
