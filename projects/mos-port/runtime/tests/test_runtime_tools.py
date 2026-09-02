from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME_ROOT))
sys.path.insert(0, str(RUNTIME_ROOT.parent / "tools"))

import audit_runtime  # noqa: E402
from audit_runtime import (  # noqa: E402
    Symbol,
    audit,
    configured_c_objects,
)
from build_runtime_archive import allowed_members  # noqa: E402
from profile_assembly import (  # noqa: E402
    exports_from_sources,
    resolve_linked_objects,
    select_linked_sources,
    validate_assembly_composition,
    validate_object_destinations,
)
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
            self.assertEqual(exports_from_sources([source]), {"_one", "_two"})

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

    def test_c_object_contract_accepts_reviewed_product_object(self) -> None:
        root = Path("obj")
        configured = configured_c_objects(
            root, ["main.o", "src/clock.o", "src/emos.o"]
        )
        self.assertEqual(configured[-1], root / "src/emos.o")

    def test_c_object_contract_rejects_duplicate_product_object(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            configured_c_objects(Path("obj"), ["main.o", "main.o"])

    def test_profile_assembly_contract_is_exact_and_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "profile.asm"
            undeclared = root / "src" / "undeclared.asm"
            source.parent.mkdir()
            source.write_text("XDEF _profile_one, _profile_two\n", encoding="utf-8")
            undeclared.write_text("XDEF _must_not_authorize\n", encoding="utf-8")
            configured = validate_assembly_composition(
                root, ["src/profile.asm"], ["src/profile.o"]
            )
            self.assertEqual(configured, {"src/profile.asm": source})
            self.assertEqual(
                exports_from_sources(configured.values()),
                {"_profile_one", "_profile_two"},
            )
            with self.assertRaisesRegex(ValueError, "unlinked"):
                select_linked_sources(configured, ["src/undeclared.asm"])
            with self.assertRaisesRegex(ValueError, "duplicate"):
                select_linked_sources(
                    configured, ["src/profile.asm", "src/profile.asm"]
                )

    def test_profile_assembly_contract_rejects_unsafe_and_incomplete_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "profile.asm"
            source.parent.mkdir()
            source.write_text("XDEF _profile\n", encoding="utf-8")
            cases = (
                ([str(source)], ["src/profile.o"], "unsafe"),
                (["../profile.asm"], ["src/profile.o"], "unsafe"),
                (["src/profile.s"], ["src/profile.o"], "unsafe"),
                (["src/missing.asm"], ["src/missing.o"], "missing"),
                (
                    ["src/profile.asm", "src/profile.asm"],
                    ["src/profile.o"],
                    "duplicate",
                ),
                (
                    ["src/profile.asm"],
                    ["src/profile.o", "src/profile.o"],
                    "duplicate",
                ),
                (["src/profile.asm"], [], "exact source mapping"),
                (["src/profile.asm"], ["src/other.o"], "exact source mapping"),
                (["src/profile.asm"], ["../profile.o"], "unsafe"),
                (["other/profile.asm"], ["other/profile.o"], "unsafe"),
            )
            for sources, objects, message in cases:
                with self.subTest(sources=sources, objects=objects):
                    with self.assertRaisesRegex(ValueError, message):
                        validate_assembly_composition(root, sources, objects)

    def test_profile_assembly_contract_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            source_dir = root / "src"
            source_dir.mkdir(parents=True)
            outside = base / "outside.asm"
            outside.write_text("XDEF _outside\n", encoding="utf-8")
            (source_dir / "profile.asm").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "escapes"):
                validate_assembly_composition(
                    root, ["src/profile.asm"], ["src/profile.o"]
                )

    def test_linked_assembly_objects_must_exist_inside_object_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "objects"
            (root / "src").mkdir(parents=True)
            linked = root / "src" / "profile.o"
            linked.write_bytes(b"object")
            self.assertEqual(
                resolve_linked_objects(root, ["src/profile.o"]), [linked]
            )
            with self.assertRaisesRegex(ValueError, "missing"):
                resolve_linked_objects(root, ["src/missing.o"])
            outside = base / "outside.o"
            outside.write_bytes(b"outside")
            linked.unlink()
            linked.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "escapes"):
                resolve_linked_objects(root, ["src/profile.o"])

            linked.unlink()
            real_root = base / "real-objects"
            (real_root / "src").mkdir(parents=True)
            (real_root / "src" / "profile.o").write_bytes(b"object")
            (root / "src").rmdir()
            root.rmdir()
            root.symlink_to(real_root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "root must not be a symlink"):
                resolve_linked_objects(root, ["src/profile.o"])

    def test_assembly_output_preflight_rejects_symlink_redirects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory) / "build"
            outside = Path(directory) / "outside"
            build.mkdir()
            outside.mkdir()
            (build / "obj").mkdir()
            (build / "obj" / "asm").symlink_to(
                outside, target_is_directory=True
            )
            with self.assertRaisesRegex(ValueError, "traverses a symlink"):
                validate_object_destinations(
                    build, Path("obj/asm"), ["src/profile.o"]
                )

    def test_runtime_provider_authority_comes_from_linked_objects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            objects = root / "objects"
            assembly = root / "assembly"
            (objects / "asm/src").mkdir(parents=True)
            (assembly / "src").mkdir(parents=True)
            c_object = objects / "main.o"
            asm_object = objects / "asm/src/profile.o"
            source = assembly / "src/profile.asm"
            archive = root / "libagon.a"
            nanoprintf = root / "nanoprintf.h"
            link_probe = root / "link-probe.o"
            runtime_archive = root / "runtime.a"
            for path in (
                c_object,
                asm_object,
                archive,
                nanoprintf,
                link_probe,
                runtime_archive,
            ):
                path.write_bytes(b"")
            source.write_text("XDEF _profile\n", encoding="utf-8")
            empty_hash = hashlib.sha256(b"").hexdigest()
            policy = {
                "c_objects": ["main.o"],
                "local_symbols": [],
                "archive_sha256": empty_hash,
                "nanoprintf_sha256": empty_hash,
                "linker_symbols": [],
                "allowed_archive_members": {},
                "forbidden_archive_members": [],
                "required_providers": {"_profile": "assembly"},
                "metadata_only_undefined": [],
            }

            def symbols(_nm: Path, target: Path) -> list[Symbol]:
                if target == c_object:
                    return [Symbol("_profile", "U", str(target))]
                if target == asm_object:
                    return [Symbol("_profile", "T", str(target))]
                if target == link_probe:
                    return [Symbol("_profile", "U", str(target))]
                return []

            completed = mock.Mock(stdout="")
            with mock.patch.object(
                audit_runtime, "run_nm", side_effect=symbols
            ), mock.patch.object(
                audit_runtime, "archive_relocations", return_value={}
            ), mock.patch.object(
                audit_runtime, "object_relocations", return_value=set()
            ), mock.patch.object(
                audit_runtime, "section_sizes", return_value={}
            ), mock.patch.object(
                audit_runtime.subprocess, "run", return_value=completed
            ):
                report, errors = audit(
                    nm=root / "nm",
                    readelf=root / "readelf",
                    ar=root / "ar",
                    size=root / "size",
                    objects_root=objects,
                    archive=archive,
                    nanoprintf=nanoprintf,
                    assembly_root=assembly,
                    local_objects=[],
                    link_probe=link_probe,
                    runtime_archive=runtime_archive,
                    policy=policy,
                    assembly_sources=["src/profile.asm"],
                    assembly_objects=["src/profile.o"],
                    profile_assembly_sources=["src/profile.asm"],
                )
            self.assertEqual(errors, [])
            self.assertEqual(report["profile_assembly_exports"], ["_profile"])

            def missing_symbols(_nm: Path, target: Path) -> list[Symbol]:
                if target == c_object or target == link_probe:
                    return [Symbol("_profile", "U", str(target))]
                return []

            with mock.patch.object(
                audit_runtime, "run_nm", side_effect=missing_symbols
            ), mock.patch.object(
                audit_runtime, "archive_relocations", return_value={}
            ), mock.patch.object(
                audit_runtime, "object_relocations", return_value=set()
            ), mock.patch.object(
                audit_runtime, "section_sizes", return_value={}
            ), mock.patch.object(
                audit_runtime.subprocess, "run", return_value=completed
            ):
                _report, errors = audit(
                    nm=root / "nm",
                    readelf=root / "readelf",
                    ar=root / "ar",
                    size=root / "size",
                    objects_root=objects,
                    archive=archive,
                    nanoprintf=nanoprintf,
                    assembly_root=assembly,
                    local_objects=[],
                    link_probe=link_probe,
                    runtime_archive=runtime_archive,
                    policy=policy,
                    assembly_sources=["src/profile.asm"],
                    assembly_objects=["src/profile.o"],
                    profile_assembly_sources=["src/profile.asm"],
                )
            self.assertTrue(any("_profile" in error for error in errors), errors)

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
