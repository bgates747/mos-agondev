from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPOSITORY_ROOT / "projects" / "mos-port" / "tools" / "assemble_zds.py"
BASE_PYTHON = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
AS = REPOSITORY_ROOT / "toolchains" / "agondev" / "bin" / "ez80-none-elf-as"


def load_wrapper():
    spec = importlib.util.spec_from_file_location("mos_assemble_zds", WRAPPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


WRAPPER = load_wrapper()


def write_mapping_tree(
    root: Path,
    *,
    source_text: str = "first\nsecond\nthird\n",
    locations: list[dict[str, object]] | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    generated = root / "generated"
    source = generated / "src" / "unit.asm"
    source.parent.mkdir(parents=True)
    source.write_text(source_text, encoding="utf-8")
    if locations is None:
        locations = [
            {"source": "src/unit.asm", "line": 1},
            {"source": "src/shared.inc", "line": 41},
            {"source": "src/unit.asm", "line": 8},
        ]
    document: dict[str, object] = {
        "schema": 2,
        "files": [
            {
                "source": "src/unit.asm",
                "output": "src/unit.asm",
                "output_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "output_locations": locations,
            }
        ],
    }
    manifest = generated / "manifest.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    return manifest, source, document


class AssembleZdsMappingTests(unittest.TestCase):
    def test_maps_root_and_included_source_lines_and_preserves_unknown_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="assemble-zds-map-") as temporary:
            manifest, source, _ = write_mapping_tree(Path(temporary))
            maintained_root, locations = WRAPPER.load_mapping(manifest, source)
            generated = str(source.resolve()).encode()
            diagnostics = b"".join(
                [
                    generated + b": Assembler messages:\n",
                    generated + b":2: Error: include failure\n",
                    generated + b":3:7: Warning: root warning\r\n",
                    generated + b":99: Error: unmapped generated line\n",
                    generated + b":not-a-line: malformed\n",
                    b"fixtures/unrelated.s:4: Error: unrelated\n",
                    b"continuation text without a path\n",
                ]
            )
            remapped = WRAPPER.remap_diagnostics(
                diagnostics, source, maintained_root, locations
            )
            self.assertIn(b"src/unit.asm: Assembler messages:\n", remapped)
            self.assertIn(b"src/shared.inc:41: Error: include failure\n", remapped)
            self.assertIn(b"src/unit.asm:8:7: Warning: root warning\r\n", remapped)
            self.assertIn(generated + b":99: Error: unmapped generated line\n", remapped)
            self.assertIn(generated + b":not-a-line: malformed\n", remapped)
            self.assertIn(b"fixtures/unrelated.s:4: Error: unrelated\n", remapped)
            self.assertTrue(remapped.endswith(b"continuation text without a path\n"))

    def test_rejects_stale_or_malformed_mapping_before_assembly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="assemble-zds-stale-") as temporary:
            manifest, source, document = write_mapping_tree(Path(temporary))
            source.write_text("changed\nsecond\nthird\n", encoding="utf-8")
            with self.assertRaisesRegex(WRAPPER.MappingError, r"stale or modified"):
                WRAPPER.load_mapping(manifest, source)

            source.write_text("first\nsecond\nthird\n", encoding="utf-8")
            document["schema"] = 999
            manifest.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(WRAPPER.MappingError, r"schema must be 2"):
                WRAPPER.load_mapping(manifest, source)

            source.write_bytes(b"\xff\n")
            document["schema"] = 2
            entry = document["files"][0]
            assert isinstance(entry, dict)
            entry["output_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            entry["output_locations"] = [{"source": "src/unit.asm", "line": 1}]
            manifest.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(WRAPPER.MappingError, r"not UTF-8"):
                WRAPPER.load_mapping(manifest, source)

    def test_rejects_traversal_duplicate_outputs_and_external_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="assemble-zds-safe-") as temporary:
            root = Path(temporary)
            manifest, source, document = write_mapping_tree(root)
            entry = document["files"][0]
            assert isinstance(entry, dict)
            locations = entry["output_locations"]
            assert isinstance(locations, list) and isinstance(locations[1], dict)
            locations[1]["source"] = "../secret.inc"
            manifest.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(WRAPPER.MappingError, r"normalized relative path"):
                WRAPPER.load_mapping(manifest, source)

            locations[1]["source"] = "src/shared.inc"
            files = document["files"]
            assert isinstance(files, list)
            files.append(
                {
                    "source": "src/other.asm",
                    "output": "../escape.asm",
                    "output_sha256": "0" * 64,
                    "output_locations": [],
                }
            )
            manifest.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(WRAPPER.MappingError, r"normalized relative path"):
                WRAPPER.load_mapping(manifest, source)

            files.pop()
            files.append(dict(entry))
            manifest.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(WRAPPER.MappingError, r"duplicate generated output"):
                WRAPPER.load_mapping(manifest, source)

            outside = root / "outside.asm"
            outside.write_text("nop\n", encoding="utf-8")
            with self.assertRaisesRegex(WRAPPER.MappingError, r"inside the manifest directory"):
                WRAPPER.load_mapping(manifest, outside)

    def test_rejects_symlinked_generated_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="assemble-zds-link-") as temporary:
            root = Path(temporary)
            manifest, source, _ = write_mapping_tree(root)
            link = source.with_name("linked.asm")
            try:
                link.symlink_to(source.name)
            except OSError as error:
                self.skipTest(f"symlinks unavailable: {error}")
            with self.assertRaisesRegex(WRAPPER.MappingError, r"must not be a symbolic link"):
                WRAPPER.load_mapping(manifest, link)


class AssembleZdsProcessTests(unittest.TestCase):
    def run_wrapper(
        self, manifest: Path, source: Path, fake_assembler: Path
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [
                BASE_PYTHON,
                "-B",
                WRAPPER_PATH,
                "--manifest",
                manifest,
                "--source",
                source,
                "--assembler",
                BASE_PYTHON,
                "--",
                fake_assembler,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_preserves_stdout_and_exit_status_while_remapping_stderr(self) -> None:
        with tempfile.TemporaryDirectory(prefix="assemble-zds-process-") as temporary:
            root = Path(temporary)
            manifest, source, _ = write_mapping_tree(root)
            fake = root / "fake_assembler.py"
            fake.write_text(
                "import os, sys\n"
                "source = os.path.realpath(sys.argv[-1])\n"
                "os.write(1, b'assembler stdout\\n')\n"
                "os.write(2, f'{source}: Assembler messages:\\n'.encode())\n"
                "os.write(2, f'{source}:2: Error: included line\\n'.encode())\n"
                "os.write(2, f'{source}:99: Error: leave generated\\n'.encode())\n"
                "os.write(2, b'raw continuation \\xff\\n')\n"
                "raise SystemExit(7)\n",
                encoding="utf-8",
            )
            completed = self.run_wrapper(manifest, source, fake)
            self.assertEqual(completed.returncode, 7)
            self.assertEqual(completed.stdout, b"assembler stdout\n")
            self.assertIn(b"src/unit.asm: Assembler messages:\n", completed.stderr)
            self.assertIn(b"src/shared.inc:41: Error: included line\n", completed.stderr)
            self.assertIn(
                str(source.resolve()).encode() + b":99: Error: leave generated\n",
                completed.stderr,
            )
            self.assertTrue(completed.stderr.endswith(b"raw continuation \xff\n"))

    def test_stale_source_fails_before_running_assembler(self) -> None:
        with tempfile.TemporaryDirectory(prefix="assemble-zds-preflight-") as temporary:
            root = Path(temporary)
            manifest, source, _ = write_mapping_tree(root)
            source.write_text("modified\nsecond\nthird\n", encoding="utf-8")
            fake = root / "must_not_run.py"
            fake.write_text("raise SystemExit(91)\n", encoding="utf-8")
            completed = self.run_wrapper(manifest, source, fake)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, b"")
            self.assertIn(b"assemble_zds: error: generated source is stale or modified", completed.stderr)

    @unittest.skipUnless(AS.is_file(), "local AgonDev assembler is unavailable")
    def test_real_gas_diagnostic_uses_included_source_location(self) -> None:
        with tempfile.TemporaryDirectory(prefix="assemble-zds-real-gas-") as temporary:
            root = Path(temporary)
            manifest, source, _ = write_mapping_tree(
                root,
                source_text=".section .text\nnot_an_ez80_instruction\n",
                locations=[
                    {"source": "src/unit.asm", "line": 1},
                    {"source": "src/shared.inc", "line": 77},
                ],
            )
            object_path = root / "unit.o"
            completed = subprocess.run(
                [
                    BASE_PYTHON,
                    "-B",
                    WRAPPER_PATH,
                    "--manifest",
                    manifest,
                    "--source",
                    source,
                    "--assembler",
                    AS,
                    "--",
                    "-march=ez80+full+adl",
                    "-o",
                    object_path,
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout, b"")
            self.assertIn(b"src/unit.asm: Assembler messages:", completed.stderr)
            self.assertIn(b"src/shared.inc:77: Error:", completed.stderr)
            self.assertNotIn(
                str(source.resolve()).encode() + b":2:", completed.stderr
            )
            self.assertFalse(object_path.exists())


if __name__ == "__main__":
    unittest.main()
