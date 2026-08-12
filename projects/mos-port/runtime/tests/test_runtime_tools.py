from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME_ROOT))

from audit_runtime import assembly_exports, configured_c_objects  # noqa: E402
from build_runtime_archive import allowed_members  # noqa: E402
from scan_formats import (  # noqa: E402
    check_golden_coverage,
    decode_string_argument,
    find_format_uses,
    parse_specifiers,
    scan,
)


class RuntimeToolTests(unittest.TestCase):
    def test_assembly_exports_ignores_comments_and_accepts_multiple_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "symbols.asm"
            source.write_text(
                "XDEF _one, _two ; XDEF _comment\n; XDEF _also_comment\n",
                encoding="utf-8",
            )
            self.assertEqual(assembly_exports(Path(directory)), {"_one", "_two"})

    def test_allow_list_rejects_duplicate_members(self) -> None:
        policy = {"allowed_archive_members": {"a": ["one.o"], "b": ["one.o"]}}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            allowed_members(policy)

    def test_c_object_contract_does_not_discover_assembly_objects(self) -> None:
        root = Path("obj")
        configured = configured_c_objects(root, ["main.o", "src/clock.o"])
        self.assertEqual(configured, [root / "main.o", root / "src/clock.o"])
        self.assertNotIn(root / "asm/src/serial.o", configured)

    def test_c_object_contract_rejects_parent_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe"):
            configured_c_objects(Path("obj"), ["../foreign.o"])

    def test_concatenated_string_argument(self) -> None:
        self.assertEqual(decode_string_argument(' "left"  "\\x20right" '), "left right")

    def test_format_call_scanner_ignores_comments(self) -> None:
        source = 'printf("%d", 3); /* printf("%lld", 4); */\n'
        uses, errors = find_format_uses(source, "sample.c", {"printf": 0})
        self.assertEqual(errors, [])
        self.assertEqual([use.format for use in uses], ["%d"])

    def test_format_specifier_parser(self) -> None:
        parsed = parse_specifiers("%06x %-*s %.*s %*lu %%")
        self.assertEqual(
            [item.spelling for item in parsed],
            ["%06x", "%-*s", "%.*s", "%*lu", "%%"],
        )
        self.assertEqual(parsed[3].length, "l")

    def test_formatter_golden_coverage_is_exact(self) -> None:
        report = {"specifiers": {"%d": 2, "%06x": 1}}
        self.assertEqual(
            check_golden_coverage(
                report,
                'GOLDEN_PATTERN("%d"); GOLDEN_PATTERN("%06x");',
            ),
            [],
        )
        errors = check_golden_coverage(
            report,
            'GOLDEN_PATTERN("%d"); GOLDEN_PATTERN("%d"); GOLDEN_PATTERN("%s");',
        )
        self.assertTrue(any("duplicate" in error for error in errors))
        self.assertTrue(any("lack host goldens" in error for error in errors))
        self.assertTrue(any("not used" in error for error in errors))

    def test_current_mos_formats_satisfy_contract(self) -> None:
        repository = RUNTIME_ROOT.parents[2]
        source = repository / "projects/mos-port/worktree"
        policy = json.loads(
            (RUNTIME_ROOT / "runtime_policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(policy["c_objects"]), 16)
        self.assertFalse(any(Path(name).parts[0] == "asm" for name in policy["c_objects"]))
        report, errors = scan(source, policy)
        self.assertEqual(errors, [])
        self.assertEqual(report["length_modifiers"].get("l"), 3)
        self.assertGreater(report["call_count"], 100)


if __name__ == "__main__":
    unittest.main()
