from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_PATH = REPOSITORY_ROOT / "projects" / "mos-port" / "tools" / "zds2gas.py"
AS = REPOSITORY_ROOT / "toolchains" / "agondev" / "bin" / "ez80-none-elf-as"
OBJDUMP = REPOSITORY_ROOT / "toolchains" / "agondev" / "bin" / "ez80-none-elf-objdump"
NM = REPOSITORY_ROOT / "toolchains" / "agondev" / "bin" / "ez80-none-elf-nm"
WORKTREE = REPOSITORY_ROOT / "projects" / "mos-port" / "worktree"
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures" / "zds2gas"


def load_frontend():
    spec = importlib.util.spec_from_file_location("mos_zds2gas", FRONTEND_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ZDS = load_frontend()


class Zds2GasUnitTests(unittest.TestCase):
    def test_committed_source_to_source_golden(self) -> None:
        source = (FIXTURES / "compatibility.zds.asm").read_text(encoding="utf-8")
        expected = (FIXTURES / "compatibility.gas.s").read_text(encoding="utf-8")
        result = ZDS.translate("fixtures/compatibility.zds.asm", source)
        self.assertEqual(result.text, expected)
        self.assertTrue(result.text.endswith("\n"))

    def test_committed_negative_diagnostic_golden(self) -> None:
        source_name = "fixtures/negative_unresolved.zds.asm"
        source = (FIXTURES / "negative_unresolved.zds.asm").read_text(encoding="utf-8")
        expected = (FIXTURES / "negative_unresolved.stderr").read_text(encoding="utf-8")
        with self.assertRaises(ZDS.FrontendError) as raised:
            ZDS.translate(source_name, source)
        self.assertEqual(f"{raised.exception}\n", expected)

    def test_preserves_comments_strings_and_current_location(self) -> None:
        source = (
            ".ASSUME ADL = 1\n"
            "SECTION TEXT\n"
            "start: jr $+3 ; $comment $F $$\n"
            "db \"$string;still string\",0\n"
            "here: EQU ($-start)\n"
        )
        result = ZDS.translate("fixture/current.asm", source)
        self.assertIn("start: jr .+3 ; $comment $F $$", result.text)
        self.assertIn('db "$string;still string",0', result.text)
        self.assertIn(".equiv here, (.-start)", result.text)

    def test_all_zds_numeric_literal_forms_are_token_normalized(self) -> None:
        source = "SECTION TEXT\ndb %FF,A0h,0Bh,00000001b,0bfffah ; FFh %AA\n"
        result = ZDS.translate("fixture/literals.asm", source)
        self.assertIn("db 0xFF,0xA0,0x0B,0b00000001,0x0bfffa", result.text)
        self.assertIn("; FFh %AA", result.text)

    def test_named_locals_are_scoped_without_source_globalization(self) -> None:
        source = (
            ".ASSUME ADL = 1\nSECTION TEXT\n"
            "SCOPE\nfirst:\n$loop: djnz $loop\n"
            "SCOPE\nsecond:\n$loop: djnz $loop\n"
        )
        result = ZDS.translate("fixture/scopes.asm", source)
        generated = [item["generated"] for item in result.analysis.mappings]
        self.assertEqual(len(generated), 2)
        self.assertNotEqual(generated[0], generated[1])
        self.assertNotIn("$loop", result.text)
        self.assertIn("s001__24_loop", result.text)
        self.assertIn("s002__24_loop", result.text)

    def test_anonymous_and_macro_local_idioms(self) -> None:
        source = (
            ".ASSUME ADL = 1\nSECTION TEXT\n"
            "WAIT: MACRO COUNT\n"
            "$$loop: ld b,COUNT\n"
            "djnz $$loop\n"
            "ENDMACRO\n"
            "start: jr $F\n"
            "$$: WAIT 2\n"
            "jr $B\n"
            "WAIT 3\n"
        )
        result = ZDS.translate("fixture/locals.asm", source)
        self.assertIn(".Lzds_m_WAIT_loop\\@", result.text)
        self.assertEqual(result.text.count("zds_WAIT"), 3)  # definition + two calls
        anonymous = next(
            item["generated"] for item in result.analysis.mappings if item["kind"] == "anonymous"
        )
        self.assertIn(f"jr {anonymous}", result.text)
        self.assertIn(f"{anonymous}: zds_WAIT 2", result.text)
        self.assertEqual(result.text.count(f"jr {anonymous}"), 2)
        self.assertNotRegex(result.text, r"(?m)^99:")

    def test_data_widths_and_wide_register_copy(self) -> None:
        source = (
            ".ASSUME ADL = 1\nSECTION TEXT\n"
            "DL 0x12345678\nDW24 0xabcdef\nLD DE,HL\n"
        )
        result = ZDS.translate("fixture/data.asm", source)
        self.assertIn("d32 0x12345678", result.text)
        self.assertIn("d24 0xabcdef", result.text)
        self.assertIn("push hl\n", result.text)
        self.assertIn("pop de\n", result.text)
        self.assertEqual(result.output_to_source[-2:], [5, 5])

    def test_reserve_fill_is_space_aware(self) -> None:
        source = (
            "DEFINE .RESET, SPACE = ROM\n"
            "SEGMENT .RESET\n"
            "DS 3\n"
            "SECTION BSS\n"
            "buffer: DS 4\n"
        )
        result = ZDS.translate("fixture/reserve.asm", source)
        self.assertIn(".skip 3, 0xff", result.text)
        self.assertIn("buffer: .skip 4", result.text)
        self.assertNotIn("buffer: .skip 4, 0xff", result.text)

    def test_unresolved_local_is_a_source_mapped_error(self) -> None:
        with self.assertRaisesRegex(ZDS.FrontendError, r"bad\.asm:3: error\[unresolved-local\]"):
            ZDS.translate("bad.asm", "SECTION TEXT\nSCOPE\njr $missing\n")

    def test_suffix_locals_are_scoped_and_case_sensitive(self) -> None:
        source = (
            "SECTION TEXT\nSCOPE\nloop?: jr loop?\n"
            "SCOPE\nloop?: jr loop?\n"
        )
        result = ZDS.translate("fixture/suffix.asm", source)
        generated = [item["generated"] for item in result.analysis.mappings]
        self.assertEqual(len(generated), 2)
        self.assertNotEqual(generated[0], generated[1])
        self.assertNotIn("loop?", result.text)
        with self.assertRaisesRegex(ZDS.FrontendError, r"error\[unresolved-local\]"):
            ZDS.translate("bad-case.asm", "SECTION TEXT\nSCOPE\nLoop?: nop\njr loop?\n")

    def test_macros_are_case_sensitive(self) -> None:
        result = ZDS.translate(
            "fixture/macro-case.asm",
            "SECTION TEXT\nThing: MACRO\nnop\nENDMACRO\nThing\nthing\n",
        )
        self.assertIn("zds_Thing\n", result.text)
        self.assertRegex(result.text, r"(?m)^thing$")

    def test_equates_are_immutable_and_identical_duplicates_are_elided(self) -> None:
        result = ZDS.translate("fixture/equ.asm", "VALUE EQU 0FFh\nVALUE EQU 0x0ff\n")
        self.assertEqual(result.text.count(".equiv VALUE"), 1)
        self.assertIn("duplicate immutable EQU", result.text)
        with self.assertRaisesRegex(ZDS.FrontendError, r"error\[conflicting-equate\]"):
            ZDS.translate("bad-equ.asm", "VALUE EQU 1\nVALUE EQU 2\n")

    def test_end_terminates_translation_unit(self) -> None:
        result = ZDS.translate("fixture/end.asm", "SECTION TEXT\nEND\n.error trailing\n")
        self.assertIn("zds2gas: END", result.text)
        self.assertNotIn("trailing", result.text)

    def test_nested_includes_are_case_compatible_and_end_returns_to_caller(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zds2gas-includes-") as temporary:
            root = Path(temporary)
            source = root / "src"
            source.mkdir()
            (source / "main.asm").write_text(
                "SECTION TEXT\n"
                'INCLUDE "FiRsT.InC"\n'
                "jr local?\n"
                "END\n"
                ".error trailing-root\n",
                encoding="utf-8",
            )
            (source / "first.inc").write_text(
                "SCOPE\n"
                'INCLUDE "SECOND.INC"\n'
                "db 2\n"
                "END\n"
                ".error trailing-first\n",
                encoding="utf-8",
            )
            (source / "second.inc").write_text(
                "local?: nop\n"
                "END\n"
                ".error trailing-second\n",
                encoding="utf-8",
            )
            expanded = ZDS.expand_translation_unit(root, "src/main.asm")
            result = ZDS.translate(
                "src/main.asm", expanded.text, locations=expanded.locations
            )
            self.assertEqual(
                [item["resolved"] for item in expanded.includes],
                ["src/first.inc", "src/second.inc"],
            )
            self.assertIn("db 2", result.text)
            self.assertIn("; zds2gas: END", result.text)
            self.assertNotIn("trailing-", result.text)
            self.assertNotIn("local?", result.text)
            local = next(
                item["generated"]
                for item in result.analysis.mappings
                if item["kind"] == "named-local"
            )
            self.assertIn(f"{local}: nop", result.text)
            self.assertIn(f"jr {local}", result.text)

            (source / "DUPE.inc").write_text("nop\n", encoding="utf-8")
            (source / "dupe.INC").write_text("nop\n", encoding="utf-8")
            (source / "ambiguous.asm").write_text(
                'INCLUDE "DuPe.Inc"\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, r"ambiguous case-insensitive include"):
                ZDS.expand_translation_unit(root, "src/ambiguous.asm")

    def test_anonymous_labels_cannot_collide_with_native_numeric_labels(self) -> None:
        source = "SECTION TEXT\nstart: jr $F\n99: nop\n$$: nop\njr $B\n"
        result = ZDS.translate("fixture/collision.asm", source)
        anonymous = next(
            item["generated"] for item in result.analysis.mappings if item["kind"] == "anonymous"
        )
        self.assertIn("99: nop", result.text)
        self.assertEqual(result.text.count(anonymous), 3)

    def test_structures_define_offsets_and_sizes_without_allocating_storage(self) -> None:
        source = (
            "SECTION TEXT\n"
            "INNER .STRUCT\n"
            "; comments and blank lines inside structures are inert\n"
            "\n"
            "first: DS 3\n"
            "second: DS 2\n"
            "INNER_SIZE .ENDSTRUCT INNER\n"
            "OUTER .STRUCT\n"
            "child: .TAG INNER\n"
            "tail: DS 4\n"
            "OUTER_SIZE .ENDSTRUCT OUTER\n"
        )
        result = ZDS.translate("fixture/struct.asm", source)
        self.assertIn(".equiv INNER.first, 0", result.text)
        self.assertIn(".equiv INNER.second, 3", result.text)
        self.assertIn(".equiv INNER_SIZE, 5", result.text)
        self.assertIn(".equiv OUTER.child, 0", result.text)
        self.assertIn(".equiv OUTER.tail, 5", result.text)
        self.assertIn(".equiv OUTER_SIZE, 9", result.text)
        self.assertNotIn(".skip", result.text)

    def test_structure_errors_are_strict_and_source_mapped(self) -> None:
        with self.assertRaisesRegex(ZDS.FrontendError, r"bad-tag\.inc:2: error\[unknown-structure-tag\]"):
            ZDS.translate("bad-tag.inc", "OUTER .STRUCT\nchild: .TAG Missing\n")
        with self.assertRaisesRegex(ZDS.FrontendError, r"bad-end\.inc:3: error\[structure-name-mismatch\]"):
            ZDS.translate("bad-end.inc", "OUTER .STRUCT\nx: DS 1\nSIZE .ENDSTRUCT Other\n")
        with self.assertRaisesRegex(ZDS.FrontendError, r"bad-member\.inc:2: error\[unsupported-structure-member\]"):
            ZDS.translate("bad-member.inc", "OUTER .STRUCT\nx: DB 1\nSIZE .ENDSTRUCT OUTER\n")


@unittest.skipUnless(AS.is_file(), "local AgonDev assembler is unavailable")
class Zds2GasObjectTests(unittest.TestCase):
    def assemble(self, source: str) -> tuple[bytes, str, str]:
        with tempfile.TemporaryDirectory(prefix="zds2gas-object-") as temporary:
            root = Path(temporary)
            translated = ZDS.translate("fixture/object.asm", source)
            source_path = root / "object.s"
            object_path = root / "object.o"
            source_path.write_text(translated.text, encoding="utf-8")
            subprocess.run(
                [AS, "-march=ez80+full+adl", source_path, "-o", object_path],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            dumped = subprocess.run(
                [OBJDUMP, "-s", "-dr", object_path],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout
            names = subprocess.run(
                [NM, "-a", object_path],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout
            return object_path.read_bytes(), dumped, names

    def test_object_bytes_and_local_symbol_visibility(self) -> None:
        source = (
            ".ASSUME ADL = 1\nSECTION TEXT\n"
            "XDEF entry\n"
            "XREF external_target\n"
            "WAIT: MACRO VALUE\n"
            "$$again: ld a,VALUE\n"
            "jr nz,$$again\n"
            "ENDMACRO\n"
            "SCOPE\n"
            "entry:\n"
            "$named: WAIT 1\n"
            "jr $F\n"
            "$$: WAIT 2\n"
            "jr $named\n"
            "call external_target\n"
            "DL 0x12345678\n"
            "DW24 0xabcdef\n"
        )
        _, dumped, names = self.assemble(source)
        compact = dumped.replace(" ", "").replace("\n", "").lower()
        self.assertIn("78563412", compact)
        self.assertIn("efcdab", compact)
        self.assertNotIn("Lzds", names)
        self.assertRegex(names, r"(?m)^[0-9a-f]+ T entry$")
        self.assertRegex(names, r"(?m)^\s+U external_target$")
        self.assertRegex(dumped, r"(?m)^\s*d:\s+r_imm24\s+external_target$")

    def test_anonymous_branch_relocation_and_disassembly_target(self) -> None:
        source = (
            ".ASSUME ADL = 1\nSECTION TEXT\n"
            "entry: jr $F\n"
            "db 011h\n"
            "$$: nop\n"
        )
        _, dumped, names = self.assemble(source)
        self.assertRegex(dumped, r"(?m)^\s*0:\s+18 01\s+jr 0x0003$")
        self.assertNotIn("R_Z80", dumped)
        self.assertNotIn("Lzds", names)

    def test_conditionals_and_repeated_anonymous_targets(self) -> None:
        source = (
            ".ASSUME ADL = 1\n"
            "SECTION TEXT\n"
            "ENABLED EQU 1\n"
            "IF ENABLED\n"
            "entry: jr $F\n"
            "jr $F\n"
            "$$: nop\n"
            "jr $F\n"
            "db 0x7e\n"
            "$$: nop\n"
            "jr $B\n"
            "ELSE\n"
            "ERROR\n"
            "ENDIF\n"
        )
        _, dumped, names = self.assemble(source)
        self.assertRegex(dumped, r"(?m)^\s*0:\s+18 02\s+jr 0x0004$")
        self.assertRegex(dumped, r"(?m)^\s*2:\s+18 00\s+jr 0x0004$")
        self.assertRegex(dumped, r"(?m)^\s*9:\s+18 fd\s+jr 0x0008$")
        self.assertNotIn("R_Z80", dumped)
        self.assertNotIn("Lzds", names)

    def test_public_mos_api_struct_offsets_match_the_maintained_layout(self) -> None:
        source = (WORKTREE / "src" / "mos_api.inc").read_text(encoding="utf-8")
        _, dumped, names = self.assemble(source)
        self.assertNotIn("Contents of section .text:", dumped)
        expected = {
            "FFOBJID_SIZE": "0000000f",
            "FIL_SIZE": "00000024",
            "DIR_SIZE": "0000002e",
            "FILINFO_SIZE": "00000116",
            "FFOBJID.objsize": "0000000b",
            "FIL.dir_ptr": "00000021",
            "DIR.fn": "0000001e",
            "FILINFO.fname": "00000016",
        }
        parsed = {
            parts[2]: parts[0]
            for line in names.splitlines()
            if len(parts := line.split(maxsplit=2)) == 3
        }
        for symbol, value in expected.items():
            self.assertEqual(parsed.get(symbol), value, symbol)


@unittest.skipUnless(WORKTREE.is_dir(), "prepared MOS worktree is unavailable")
class Zds2GasCorpusTests(unittest.TestCase):
    def test_real_tree_is_deterministic_and_all_units_assemble(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zds2gas-tree-") as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first_manifest = ZDS.translate_tree(WORKTREE, first, check=False)
            second_manifest = ZDS.translate_tree(WORKTREE, second, check=False)
            self.assertEqual(first_manifest, second_manifest)
            self.assertEqual(len(first_manifest["files"]), 15)
            self.assertEqual(len(first_manifest["macros"]), 17)
            self.assertEqual(
                first_manifest["input_commit"],
                "5f67b1ca77eb7a77d3b37cc7b029db51f0d1548e",
            )
            self.assertEqual(
                (first / "manifest.json").read_bytes(),
                (second / "manifest.json").read_bytes(),
            )

            for entry in first_manifest["files"]:
                generated = (first / entry["output"]).read_text(encoding="utf-8")
                self.assertTrue(
                    generated.startswith(
                        "; generated by zds2gas frontend schema 2\n"
                        f"; translation unit: {entry['source']}\n"
                        "; agon-mos input commit: "
                        "5f67b1ca77eb7a77d3b37cc7b029db51f0d1548e\n"
                        "; expanded input sha256: "
                    ),
                    entry["source"],
                )

            object_root = root / "objects"
            assembly_files = sorted(first.glob("src/*.asm")) + sorted(first.glob("src_startup/*.asm"))
            self.assertEqual(len(assembly_files), 15)
            for source in assembly_files:
                relative = source.relative_to(first)
                target = (object_root / relative).with_suffix(".o")
                target.parent.mkdir(parents=True, exist_ok=True)
                completed = subprocess.run(
                    [
                        AS,
                        "-march=ez80+full+adl",
                        "-I", first / "src",
                        "-I", first / "src_startup",
                        "-I", REPOSITORY_ROOT / "toolchains" / "agondev" / "include",
                        source,
                        "-o", target,
                    ],
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=source.parent,
                )
                self.assertEqual(completed.returncode, 0, f"{relative}: {completed.stderr}")

            manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            sd = next(item for item in manifest["files"] if item["source"] == "src/sd.asm")
            self.assertGreater(sd["output_lines"], sd["input_lines"])
            self.assertTrue(sd["includes"])
            included_sources = {item["source"] for item in sd["source_files"]}
            self.assertIn("src/macros.inc", included_sources)
            self.assertIn("src/equs.inc", included_sources)
            self.assertIn("toolchain/ez80f92.inc", included_sources)
            self.assertTrue(all(len(item["sha256"]) == 64 for item in sd["source_files"]))
            self.assertEqual(len(sd["scopes"]), 16)  # implicit file scope + 15 SCOPEs


if __name__ == "__main__":
    unittest.main()
