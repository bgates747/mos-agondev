from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "binary_compare"


def load_script(name: str):
    path = ROOT / "projects" / "binary-compare" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"binary_compare_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


analyze = load_script("analyze")
collect_candidate = load_script("collect_candidate")
fetch_reference = load_script("fetch_reference")
verify_report = load_script("verify_report")


class BinaryAnalysisTests(unittest.TestCase):
    def test_zds_parser_captures_ranges_symbols_absolute_values_and_build(self) -> None:
        modules, symbols, metadata = analyze.parse_zds_map(
            (FIXTURES / "zds-map.txt").read_text(encoding="utf-8")
        )
        self.assertEqual([item.segment for item in modules], ["CODE", "BSS", "TEXT"])
        self.assertEqual(modules[0].size, 0x10)
        by_name = {item.name: item for item in symbols}
        self.assertEqual(by_name["_sample"].address, 0x100)
        self.assertEqual(by_name["__len_bss"].address_space, "A")
        self.assertEqual(by_name["__len_bss"].address, 4)
        self.assertIn("5.3.5", metadata["zds"])
        self.assertIn("6.25", metadata["linker"])
        self.assertEqual(metadata["compiler_options"], [])
        self.assertEqual(metadata["assembler_options"], [])

    def test_gnu_parser_and_split_code_text_mapping_cover_the_object(self) -> None:
        zds, _, _ = analyze.parse_zds_map(
            (FIXTURES / "zds-map.txt").read_text(encoding="utf-8")
        )
        gnu = analyze.parse_gnu_map(
            (FIXTURES / "gnu-map.txt").read_text(encoding="utf-8")
        )
        code = next(item for item in zds if item.segment == "CODE")
        text = next(item for item in zds if item.segment == "TEXT")
        code_candidate = analyze.candidate_range_for(code, gnu, zds)
        text_candidate = analyze.candidate_range_for(text, gnu, zds)
        assert code_candidate and text_candidate
        self.assertEqual((code_candidate.address, code_candidate.size), (0x200, 0x10))
        self.assertEqual((text_candidate.address, text_candidate.size), (0x210, 4))
        self.assertEqual(code_candidate.end, text_candidate.address)

    def test_nm_parser_retains_elf_symbol_size_for_c_anchor_bounds(self) -> None:
        symbols = analyze.parse_nm("00000100 0000002a T _function\n")
        self.assertEqual(symbols[0].name, "_function")
        self.assertEqual(symbols[0].address, 0x100)
        self.assertEqual(symbols[0].size, 0x2A)

    def test_relocation_mask_accepts_only_recognized_address_values(self) -> None:
        reference = bytes.fromhex("cd 34 12 00 c9")
        candidate = bytes.fromhex("cd 78 56 00 c9")
        spans = analyze.relocation_byte_spans(
            reference,
            candidate,
            (0x1000, 0x2000),
            (0x3000, 0x4000),
            {(0x1234, 0x5678): "@target"},
        )
        self.assertEqual(spans, [{
            "offset": 1,
            "width": 3,
            "reference_value": 0x1234,
            "candidate_value": 0x5678,
            "token": "@target",
        }])
        self.assertIsNone(
            analyze.relocation_byte_spans(
                reference,
                candidate,
                (0x1000, 0x2000),
                (0x3000, 0x4000),
                {},
            )
        )

    def test_equal_module_relative_targets_normalize_but_constants_do_not(self) -> None:
        self.assertEqual(
            analyze.paired_value_token(0x1012, 0x3012, {}, (0x1000, 0x1100), (0x3000, 0x3100)),
            "@self+0x12",
        )
        self.assertIsNone(
            analyze.paired_value_token(0x42, 0x43, {}, (0x1000, 0x1100), (0x3000, 0x3100))
        )

    def test_symbol_order_reports_reordering_without_claiming_equivalence(self) -> None:
        reference = [
            analyze.Symbol("a", 0x100, "C", "unit", "CODE"),
            analyze.Symbol("b", 0x110, "C", "unit", "CODE"),
        ]
        candidate = [
            analyze.Symbol("a", 0x220, "C", "", ""),
            analyze.Symbol("b", 0x200, "C", "", ""),
        ]
        comparisons = analyze.symbol_order_comparisons(reference, candidate)
        self.assertEqual(comparisons[0]["classification"], "reordered")
        self.assertEqual(comparisons[0]["candidate_order"], ["b", "a"])

    def test_zds_build_include_paths_are_sanitized_in_durable_evidence(self) -> None:
        self.assertEqual(
            analyze.sanitize_zds_option('-stdinc:"C:\\Zilog\\include"'),
            "-stdinc:<ZDS-standard-includes>",
        )
        self.assertEqual(
            analyze.sanitize_zds_option('-usrinc:"Y:\\src"'),
            "-usrinc:<release-project-includes>",
        )


class CandidateCollectionTests(unittest.TestCase):
    def test_preparation_diff_is_tied_to_source_head_and_dirty_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            prepared = root / "prepared"
            source.mkdir()
            prepared.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=source,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Binary Test"], cwd=source, check=True
            )
            (source / "main.c").write_text("old\n", encoding="utf-8")
            subprocess.run(["git", "add", "main.c"], cwd=source, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"],
                cwd=source,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source,
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            (prepared / "main.c").write_text("new\n", encoding="utf-8")
            provenance = {
                "source": {"head": head, "tracked_dirty": False},
                "files": [{"path": "main.c"}],
            }
            changes = collect_candidate.preparation_changes(source, prepared, provenance)
            self.assertEqual([item["path"] for item in changes], ["main.c"])
            self.assertIn("-old", changes[0]["diff"])
            (source / "main.c").write_text("dirty\n", encoding="utf-8")
            with self.assertRaises(collect_candidate.CollectionError):
                collect_candidate.preparation_changes(source, prepared, provenance)


class ReferenceImportTests(unittest.TestCase):
    def test_latest_release_metadata_and_asset_inventory_are_exact(self) -> None:
        assets = {
            name: {
                "size": index,
                "sha256": str(index) * 64,
                "url": f"https://example.invalid/{name}",
            }
            for index, name in enumerate(("MOS.bin", "MOS.hex", "MOS.map"), start=1)
        }
        manifest = {
            "release": {
                "tag": "v1",
                "name": "v1",
                "published_at": "today",
                "url": "https://example.invalid/release",
                "commit": "a" * 40,
            },
            "assets": assets,
        }
        release = {
            "tag_name": "v1",
            "name": "v1",
            "published_at": "today",
            "html_url": "https://example.invalid/release",
            "assets": [
                {
                    "name": name,
                    "size": entry["size"],
                    "browser_download_url": entry["url"],
                }
                for name, entry in assets.items()
            ],
        }
        fetch_reference.validate_latest_release(manifest, release, "a" * 40)
        release["tag_name"] = "v2"
        with self.assertRaises(fetch_reference.ReferenceError):
            fetch_reference.validate_latest_release(manifest, release, "a" * 40)

    def test_import_is_hash_checked_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            assets = {}
            for name, data in {
                "MOS.bin": b"bin",
                "MOS.hex": b"hex-data",
                "MOS.map": b"map-data",
            }.items():
                (source / name).write_bytes(data)
                assets[name] = {
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "url": f"https://github.com/AgonPlatform/agon-mos/releases/download/test/{name}",
                }
            manifest = {
                "schema": 1,
                "release": {"tag": "test"},
                "assets": assets,
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            loaded = fetch_reference.load_manifest(manifest_path)
            output.mkdir()
            for name in sorted(assets):
                fetch_reference.materialize_asset(name, loaded["assets"][name], output, source)
                fetch_reference.materialize_asset(name, loaded["assets"][name], output, source)
            self.assertEqual((output / "MOS.bin").read_bytes(), b"bin")
            (output / "MOS.bin").write_bytes(b"bad")
            with self.assertRaises(fetch_reference.ReferenceError):
                fetch_reference.verify_asset(output / "MOS.bin", "MOS.bin", assets["MOS.bin"])


class ReportVerificationTests(unittest.TestCase):
    def test_reviewed_view_rejects_high_priority_assembly_queue(self) -> None:
        report = {
            "candidate": {
                "source": {"head": "0" * 40, "tracked_dirty": False},
                "binary": {"size": 1, "sha256": "1" * 64},
                "elf_sha256": "2" * 64,
                "map_sha256": "3" * 64,
                "artifact_manifest_sha256": "4" * 64,
            },
            "reference": {},
            "source_divergence": [],
            "preparation_changes": [],
            "raw_image_difference": {},
            "summary": {"high_priority_review_entries": 1},
        }
        with self.assertRaises(verify_report.VerificationError):
            verify_report.evidence_view(report)

    def test_reviewed_view_is_a_bounded_stable_projection(self) -> None:
        report = {
            "candidate": {
                "source": {"head": "0" * 40, "tracked_dirty": False},
                "binary": {"size": 1, "sha256": "1" * 64},
                "elf_sha256": "2" * 64,
                "map_sha256": "3" * 64,
                "artifact_manifest_sha256": "4" * 64,
                "ignored": "detail",
            },
            "reference": {"release": {"tag": "test"}},
            "source_divergence": [],
            "preparation_changes": [{"path": "main.c", "diff": "large"}],
            "raw_image_difference": {"reference_size": 1},
            "summary": {"high_priority_review_entries": 0, "assembly_slices": 1},
        }
        view = verify_report.evidence_view(report)
        self.assertEqual(view["preparation_paths"], ["main.c"])
        self.assertNotIn("ignored", view["candidate"])


if __name__ == "__main__":
    unittest.main()
