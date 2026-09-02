from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORDER = ROOT / "projects" / "mos-port" / "tools" / "record_target_step.py"

SPEC = importlib.util.spec_from_file_location("record_target_step", RECORDER)
assert SPEC is not None and SPEC.loader is not None
record_target_step = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = record_target_step
SPEC.loader.exec_module(record_target_step)


FAKE_TOOL = r'''#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import sys

if sys.argv[1:] == ["--version"]:
    print("synthetic-target-tool 1.0")
    raise SystemExit(0)
if "-###" in sys.argv:
    selected = Path(sys.argv[sys.argv.index("--driver-tool") + 1])
    print(json.dumps(str(selected)) + ' "--synthetic-assembly"', file=sys.stderr)
    raise SystemExit(0)

parser = argparse.ArgumentParser()
parser.add_argument("--source", required=True, type=Path)
parser.add_argument("--input", action="append", type=Path, default=[])
parser.add_argument("--output", required=True, type=Path)
parser.add_argument("--depfile", required=True, type=Path)
parser.add_argument("--secondary", type=Path)
parser.add_argument("--marker", type=Path)
parser.add_argument("--mutate", type=Path)
parser.add_argument("--fail", action="store_true")
parser.add_argument("--assert-sanitized", action="store_true")
parser.add_argument("--wrong-dependency-target", action="store_true")
parser.add_argument("--driver-tool", type=Path)
parser.add_argument("response", nargs="?")
args = parser.parse_args()
if args.assert_sanitized:
    forbidden = {"CPATH", "LIBRARY_PATH", "SOURCE_DATE_EPOCH"}
    if forbidden.intersection(os.environ):
        raise SystemExit(8)
    if os.environ.get("LC_ALL") != "C" or os.environ.get("LANG") != "C":
        raise SystemExit(7)
if args.marker is not None:
    args.marker.write_text("executed", encoding="utf-8")
if args.fail:
    raise SystemExit(9)
args.output.write_bytes(
    args.source.read_bytes() + b"|" + b"|".join(path.read_bytes() for path in args.input)
)
dependencies = [args.source, *args.input]
args.depfile.write_text(
    ("wrong-output.o" if args.wrong_dependency_target else str(args.output))
    + ": "
    + " ".join(str(path) for path in dependencies)
    + "\n",
    encoding="utf-8",
)
if args.secondary is not None:
    args.secondary.write_text("secondary", encoding="utf-8")
if args.mutate is not None:
    args.mutate.write_text("changed", encoding="utf-8")
'''


class TargetStepProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.build = self.root / "build"
        self.source_root = self.root / "source"
        self.toolchain = self.root / "toolchain"
        self.provenance = self.root / "evidence"
        for path in (self.build, self.source_root, self.toolchain, self.provenance):
            path.mkdir()
        record_target_step.initialize_directory(self.provenance)
        self.tool = self.toolchain / "fake-target-tool"
        self.tool.write_text(FAKE_TOOL, encoding="utf-8")
        self.tool.chmod(0o755)
        self.source = self.source_root / "unit.c"
        self.source.write_text("source", encoding="utf-8")
        self.header = self.source_root / "unit.h"
        self.header.write_text("header", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def command(
        self,
        *,
        kind: str = "c-compile",
        record: Path | None = None,
        output: Path | None = None,
        depfile: Path | None = None,
        inputs: list[Path] | None = None,
        extra_recorder: list[str] | None = None,
        extra_tool: list[str] | None = None,
    ) -> list[str]:
        record = record or self.provenance / "step.json"
        output = output or self.build / "unit.o"
        depfile = depfile or self.build / "unit.d"
        inputs = [self.header] if inputs is None else inputs
        command = [
            sys.executable,
            "-B",
            str(RECORDER),
            "--kind",
            kind,
            "--record",
            str(record),
            "--cwd",
            str(self.build),
            "--root",
            f"BUILD_TOOL={ROOT}",
            "--root",
            f"BUILD={self.build}",
            "--root",
            f"PREPARED={self.source_root}",
            "--root",
            f"TOOLCHAIN={self.toolchain}",
            "--root",
            f"PROVENANCE={self.provenance}",
            "--source",
            str(self.source),
        ]
        for path in inputs:
            command.extend(("--input", str(path)))
        command.extend(("--output", str(output), "--depfile", str(depfile)))
        command.extend(extra_recorder or [])
        command.extend(
            [
                "--",
                str(self.tool),
                "--source",
                str(self.source),
            ]
        )
        for path in inputs:
            command.extend(("--input", str(path)))
        command.extend(("--output", str(output), "--depfile", str(depfile)))
        command.extend(extra_tool or [])
        return command

    def execute(
        self, command: list[str], success: bool = True
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            cwd=self.build,
            env={
                **os.environ,
                "CPATH": "/poison/include",
                "LIBRARY_PATH": "/poison/lib",
                "SOURCE_DATE_EPOCH": "123456789",
            },
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if success and completed.returncode != 0:
            self.fail(f"command failed:\n{completed.stdout}\n{completed.stderr}")
        if not success:
            self.assertNotEqual(completed.returncode, 0)
        return completed

    def test_records_actual_command_dependencies_tools_and_stability(self) -> None:
        nested = self.toolchain / "nested-as"
        nested.write_text(FAKE_TOOL, encoding="utf-8")
        nested.chmod(0o755)
        record_path = self.provenance / "compile" / "unit.json"
        self.execute(
            self.command(
                record=record_path,
                extra_recorder=[
                    "--nested-executable",
                    str(nested),
                    "--driver-selected-executable",
                    str(nested),
                ],
                extra_tool=[
                    "--driver-tool",
                    str(nested),
                    "--assert-sanitized",
                ],
            )
        )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["step_kind"], "c-compile")
        self.assertEqual(record["input_stability"], "verified-before-and-after")
        self.assertEqual(record["working_directory"], "${BUILD}")
        self.assertEqual(record["output"]["path"], "${BUILD}/unit.o")
        self.assertEqual(
            [item["path"] for item in record["dependencies"]],
            ["${PREPARED}/unit.c", "${PREPARED}/unit.h"],
        )
        self.assertEqual(len(record["executables"]), 2)
        self.assertEqual(
            record["driver_selection"][0]["selected_executable"],
            "${TOOLCHAIN}/nested-as",
        )
        self.assertEqual(
            record["driver_selection"][0]["selected_invocation"][0],
            "${TOOLCHAIN}/nested-as",
        )
        self.assertIn(
            "${TOOLCHAIN}/nested-as",
            record["driver_selection"][0]["probe_output"],
        )
        self.assertTrue(
            all(item["version_output_sha256"] for item in record["executables"])
        )
        for executable in record["executables"]:
            self.assertEqual(
                executable["version_output_sha256"],
                record_target_step.sha256_bytes(
                    executable["version_output"].encode("utf-8")
                ),
            )
        self.assertEqual(record["environment"]["variables"]["LC_ALL"], "C")
        self.assertEqual(
            record["environment"]["source_date_epoch"]["disposition"],
            "cleared",
        )
        self.assertIsNone(record["environment"]["source_date_epoch"]["value"])
        self.assertIn("CPATH", record["environment"]["cleared_variables"])
        self.assertEqual(record["response_files"], [])
        self.assertEqual(
            record["recorder"]["path"],
            "${BUILD_TOOL}/projects/mos-port/tools/record_target_step.py",
        )
        self.assertEqual(
            record["session"]["path"],
            "${PROVENANCE}/.mos-agondev-provenance-session.json",
        )
        self.assertIn("${TOOLCHAIN}/fake-target-tool", record["command"])
        self.assertNotIn(str(self.root), json.dumps(record))

    def test_driver_selection_mismatch_fails_before_execution(self) -> None:
        selected = self.toolchain / "selected-as"
        selected.write_text(FAKE_TOOL, encoding="utf-8")
        selected.chmod(0o755)
        incorrectly_declared = self.toolchain / "wrong-as"
        incorrectly_declared.write_text(FAKE_TOOL, encoding="utf-8")
        incorrectly_declared.chmod(0o755)
        marker = self.build / "marker"
        completed = self.execute(
            self.command(
                extra_recorder=[
                    "--nested-executable",
                    str(selected),
                    "--nested-executable",
                    str(incorrectly_declared),
                    "--driver-selected-executable",
                    str(incorrectly_declared),
                ],
                extra_tool=[
                    "--driver-tool",
                    str(selected),
                    "--marker",
                    str(marker),
                ],
            ),
            success=False,
        )
        self.assertIn("observed 0", completed.stderr)
        self.assertFalse(marker.exists())

    def test_direct_assembler_kind_is_supported(self) -> None:
        record_path = self.provenance / "assembly.json"
        self.execute(self.command(kind="direct-assembly", record=record_path))
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["step_kind"], "direct-assembly")
        self.assertEqual(record["executables"][0]["path"], "${TOOLCHAIN}/fake-target-tool")

    def test_stale_output_or_record_blocks_execution(self) -> None:
        marker = self.build / "marker"
        output = self.build / "unit.o"
        output.write_bytes(b"stale")
        completed = self.execute(
            self.command(output=output, extra_tool=["--marker", str(marker)]),
            success=False,
        )
        self.assertIn("refusing stale build output", completed.stderr)
        self.assertFalse(marker.exists())

        output.unlink()
        record = self.provenance / "step.json"
        record.write_text("{}\n", encoding="utf-8")
        completed = self.execute(
            self.command(record=record, extra_tool=["--marker", str(marker)]),
            success=False,
        )
        self.assertIn("refusing stale provenance record", completed.stderr)
        self.assertFalse(marker.exists())

    def test_undeclared_dependency_fails_without_record(self) -> None:
        record = self.provenance / "step.json"
        completed = self.execute(
            self.command(inputs=[], extra_tool=["--input", str(self.header)]),
            success=False,
        )
        self.assertIn("was not hashed before execution", completed.stderr)
        self.assertFalse(record.exists())
        self.assertFalse((self.build / "unit.o").exists())
        self.assertFalse((self.build / "unit.d").exists())

    def test_wrong_dependency_target_fails_and_cleans_outputs(self) -> None:
        record = self.provenance / "step.json"
        completed = self.execute(
            self.command(extra_tool=["--wrong-dependency-target"]),
            success=False,
        )
        self.assertIn("target does not match build output", completed.stderr)
        self.assertFalse(record.exists())
        self.assertFalse((self.build / "unit.o").exists())
        self.assertFalse((self.build / "unit.d").exists())

    def test_input_mutation_fails_without_record(self) -> None:
        record = self.provenance / "step.json"
        completed = self.execute(
            self.command(extra_tool=["--mutate", str(self.header)]),
            success=False,
        )
        self.assertIn("changed during execution", completed.stderr)
        self.assertFalse(record.exists())
        self.assertFalse((self.build / "unit.o").exists())
        self.assertFalse((self.build / "unit.d").exists())

    def test_failed_command_never_records_success(self) -> None:
        record = self.provenance / "step.json"
        completed = self.execute(self.command(extra_tool=["--fail"]), success=False)
        self.assertIn("exit status 9", completed.stderr)
        self.assertFalse(record.exists())

    def test_link_record_binds_ordered_inputs_secondary_output_and_producer(self) -> None:
        object_record = self.provenance / "compile" / "unit.json"
        object_path = self.build / "unit.o"
        object_depfile = self.build / "unit.d"
        self.execute(
            self.command(
                record=object_record,
                output=object_path,
                depfile=object_depfile,
            )
        )

        link_source = self.source_root / "layout.ld"
        link_source.write_text("layout", encoding="utf-8")
        linked = self.build / "firmware.elf"
        depfile = self.build / "firmware.d"
        map_file = self.build / "firmware.map"
        link_record = self.provenance / "link" / "firmware.json"
        command = self.command(
            kind="final-link",
            record=link_record,
            output=linked,
            depfile=depfile,
            inputs=[object_path],
            extra_recorder=[
                "--secondary-output",
                str(map_file),
                "--link-input",
                str(object_path),
                "--producer",
                str(object_path),
                str(object_record),
            ],
            extra_tool=["--secondary", str(map_file)],
        )
        source_index = command.index(str(self.source), command.index("--") + 1)
        command[source_index] = str(link_source)
        recorder_source_index = command.index(str(self.source))
        command[recorder_source_index] = str(link_source)
        self.execute(command)
        record = json.loads(link_record.read_text(encoding="utf-8"))
        self.assertEqual(record["step_kind"], "final-link")
        self.assertEqual(record["ordered_link_inputs"][0]["path"], "${BUILD}/unit.o")
        self.assertEqual(record["secondary_outputs"][0]["path"], "${BUILD}/firmware.map")
        self.assertEqual(
            record["producer_records"][0]["record"],
            "${PROVENANCE}/compile/unit.json",
        )

    def test_changed_producer_record_is_rejected_before_link(self) -> None:
        object_record = self.provenance / "compile" / "unit.json"
        object_path = self.build / "unit.o"
        object_depfile = self.build / "unit.d"
        self.execute(
            self.command(
                record=object_record,
                output=object_path,
                depfile=object_depfile,
            )
        )
        record = json.loads(object_record.read_text(encoding="utf-8"))
        record["output"]["sha256"] = "0" * 64
        object_record.write_text(json.dumps(record), encoding="utf-8")
        marker = self.build / "marker"
        completed = self.execute(
            self.command(
                kind="final-link",
                record=self.provenance / "link.json",
                output=self.build / "linked.elf",
                depfile=self.build / "linked.d",
                inputs=[],
                extra_recorder=[
                    "--link-input",
                    str(object_path),
                    "--producer",
                    str(object_path),
                    str(object_record),
                ],
                extra_tool=["--input", str(object_path), "--marker", str(marker)],
            ),
            success=False,
        )
        self.assertIn("producer record output digest mismatch", completed.stderr)
        self.assertFalse(marker.exists())

    def test_cross_session_producer_record_is_rejected_before_link(self) -> None:
        object_record = self.provenance / "compile" / "unit.json"
        object_path = self.build / "unit.o"
        object_depfile = self.build / "unit.d"
        self.execute(
            self.command(
                record=object_record,
                output=object_path,
                depfile=object_depfile,
            )
        )
        record = json.loads(object_record.read_text(encoding="utf-8"))
        record["session"]["sha256"] = "0" * 64
        object_record.write_text(json.dumps(record), encoding="utf-8")
        marker = self.build / "marker"
        completed = self.execute(
            self.command(
                kind="final-link",
                record=self.provenance / "link.json",
                output=self.build / "linked.elf",
                depfile=self.build / "linked.d",
                inputs=[],
                extra_recorder=[
                    "--link-input",
                    str(object_path),
                    "--producer",
                    str(object_path),
                    str(object_record),
                ],
                extra_tool=["--input", str(object_path), "--marker", str(marker)],
            ),
            success=False,
        )
        self.assertIn("different build session", completed.stderr)
        self.assertFalse(marker.exists())

    def test_duplicate_producer_is_rejected_before_link(self) -> None:
        object_record = self.provenance / "compile" / "unit.json"
        object_path = self.build / "unit.o"
        object_depfile = self.build / "unit.d"
        self.execute(
            self.command(
                record=object_record,
                output=object_path,
                depfile=object_depfile,
            )
        )
        marker = self.build / "marker"
        producer = ["--producer", str(object_path), str(object_record)]
        completed = self.execute(
            self.command(
                kind="final-link",
                record=self.provenance / "link.json",
                output=self.build / "linked.elf",
                depfile=self.build / "linked.d",
                inputs=[],
                extra_recorder=[
                    "--link-input",
                    str(object_path),
                    *producer,
                    *producer,
                ],
                extra_tool=["--input", str(object_path), "--marker", str(marker)],
            ),
            success=False,
        )
        self.assertIn("duplicate input", completed.stderr)
        self.assertFalse(marker.exists())

    def test_dependency_parser_handles_continuations_and_escaped_space(self) -> None:
        depfile = self.build / "input.d"
        depfile.write_text(
            "output.o: one.c two\\ file.h \\\n three.h\n",
            encoding="utf-8",
        )
        self.assertEqual(
            record_target_step.parse_depfile(depfile),
            ["one.c", "two file.h", "three.h"],
        )

        depfile.write_text(
            "output.o: \\\n one.c two.h\n\none.c:\ntwo.h:\n",
            encoding="utf-8",
        )
        self.assertEqual(
            record_target_step.parse_depfile(depfile),
            ["one.c", "two.h"],
        )

    def test_initialization_refuses_stale_or_symlinked_directory(self) -> None:
        with self.assertRaisesRegex(
            record_target_step.ProvenanceError, "is not empty"
        ):
            record_target_step.initialize_directory(self.provenance)

        outside = self.root / "outside-evidence"
        outside.mkdir()
        alias = self.root / "evidence-alias"
        alias.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(
            record_target_step.ProvenanceError, "symbolic-link component"
        ):
            record_target_step.initialize_directory(alias)

    def test_independent_initializations_have_distinct_session_ids(self) -> None:
        first = json.loads(
            (
                self.provenance
                / record_target_step.SESSION_MARKER
            ).read_text(encoding="utf-8")
        )
        second_root = self.root / "second-evidence"
        second = record_target_step.initialize_directory(second_root)
        self.assertRegex(first["session_id"], r"^[0-9a-f]{32}$")
        self.assertRegex(second["session_id"], r"^[0-9a-f]{32}$")
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertNotEqual(
            record_target_step.sha256_file(
                self.provenance / record_target_step.SESSION_MARKER
            ),
            record_target_step.sha256_file(
                second_root / record_target_step.SESSION_MARKER
            ),
        )

    def test_symlinked_input_parent_escape_fails_before_execution(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        escaped = outside / "escaped.h"
        escaped.write_text("escaped", encoding="utf-8")
        alias = self.source_root / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        marker = self.build / "marker"
        completed = self.execute(
            self.command(
                inputs=[alias / "escaped.h"],
                extra_tool=["--marker", str(marker)],
            ),
            success=False,
        )
        self.assertIn("symbolic-link component", completed.stderr)
        self.assertFalse(marker.exists())

    def test_symlinked_output_parent_escape_fails_before_execution(self) -> None:
        outside = self.root / "outside-output"
        outside.mkdir()
        alias = self.build / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        marker = self.build / "marker"
        completed = self.execute(
            self.command(
                output=alias / "unit.o",
                depfile=alias / "unit.d",
                extra_tool=["--marker", str(marker)],
            ),
            success=False,
        )
        self.assertIn("symbolic-link component", completed.stderr)
        self.assertFalse(marker.exists())

    def test_response_file_must_be_explicit_and_is_hashed(self) -> None:
        response = self.source_root / "args.rsp"
        response.write_text("--synthetic", encoding="utf-8")
        command = self.command(extra_tool=[f"@{response}"])
        completed = self.execute(command, success=False)
        self.assertIn("do not exactly match", completed.stderr)
        self.assertFalse((self.build / "unit.o").exists())

        self.execute(
            self.command(
                record=self.provenance / "response.json",
                extra_recorder=["--response-file", str(response)],
                extra_tool=[f"@{response}"],
            )
        )
        record = json.loads(
            (self.provenance / "response.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["response_files"][0]["path"], "${PREPARED}/args.rsp")

    def test_nested_response_file_is_rejected_before_execution(self) -> None:
        nested = self.source_root / "nested.rsp"
        nested.write_text("--synthetic", encoding="utf-8")
        response = self.source_root / "args.rsp"
        response.write_text(f"@{nested}\n", encoding="utf-8")
        marker = self.build / "marker"
        completed = self.execute(
            self.command(
                extra_recorder=["--response-file", str(response)],
                extra_tool=[f"@{response}", "--marker", str(marker)],
            ),
            success=False,
        )
        self.assertIn(
            "nested response-file references are unsupported",
            completed.stderr,
        )
        self.assertFalse(marker.exists())



if __name__ == "__main__":
    unittest.main()
