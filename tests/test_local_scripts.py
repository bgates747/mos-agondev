from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = REPOSITORY_ROOT / "scripts" / "setup_local.py"
PREPARE_SCRIPT = REPOSITORY_ROOT / "scripts" / "prepare_mos_worktree.py"
PREPARATION_METADATA = ".mos-agondev-worktree.json"

AGONDEV_TOOLS = (
    "agondev-config",
    "ez80-none-elf-clang",
    "ez80-none-elf-as",
    "ez80-none-elf-ld",
    "ez80-none-elf-objcopy",
    "ez80-none-elf-objdump",
    "ez80-none-elf-readelf",
    "ez80-none-elf-size",
    "ez80-none-elf-nm",
)


class LocalScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="mos-agondev-scripts-")
        self.base = Path(self._temporary.name)
        self.repository = self.base / "mos-agondev"
        self.repository.mkdir()
        (self.repository / "projects" / "mos-port").mkdir(parents=True)
        self.agondev = self.base / "agondev"
        self.mos = self.base / "agon-mos"
        self._make_agondev(self.agondev)
        self._make_mos(self.mos)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    @staticmethod
    def _make_agondev(root: Path) -> None:
        binary_directory = root / "release" / "bin"
        binary_directory.mkdir(parents=True)
        for name in AGONDEV_TOOLS:
            tool = binary_directory / name
            tool.write_bytes(b"#!/bin/sh\nexit 0\n")
            tool.chmod(0o755)

    @staticmethod
    def _write(root: Path, relative: str, data: bytes) -> None:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def _make_mos(self, root: Path) -> None:
        root.mkdir()
        subprocess.run(["git", "init", "-q", os.fspath(root)], check=True)
        self._write(root, "MOS.zdsproj", b"<project/>\r\n")
        self._write(
            root,
            "src/defines.h",
            b"#ifndef MOS_DEFINES_H\r\n"
            b"#define MOS_DEFINES_H\r\n"
            b"extern void _heapbot[];\r\n"
            b"extern void _heaptop[];\r\n"
            b"extern void _stack[];\r\n"
            b"extern void _low_data[];\r\n"
            b"extern void _low_bss[];\r\n"
            b"extern void _low_romdata[];\r\n"
            b"#endif\r\n",
        )
        self._write(
            root,
            "main.c",
            b"#include <eZ80.h>\r\n"
            b"#include <defines.h>\r\n"
            b"#include <CTYPE.h>\r\n"
            b"#include <String.h>\r\n"
            b"int quickrand(void) {\r\n"
            b'\tasm("ld a,r\\n"\r\n'
            b'\t\t"ld hl,0\\n"\r\n'
            b'\t\t"ld l,a\\n");\r\n'
            b"}\r\n"
            b"extern void _heapbot[];\r\n",
        )
        self._write(
            root,
            "src/mos.c",
            b"#include <eZ80.h>\r\nextern void sysvars[];\r\n",
        )
        self._write(root, "src/mos_editor.c", b"#include <eZ80.h>\r\n")
        self._write(root, "src/timer.c", b"#include <eZ80.h>\r\n")
        self._write(root, "src/uart.c", b"#include <eZ80.h>\r\n")
        self._write(
            root,
            "src/clock.h",
            b"#ifndef RTC_H\r\n"
            b"#define RTC_H\r\n"
            b"\r\n"
            b"#define EPOCH_YEAR\t1980\r\n"
            b"#endif RTC_H\r\n",
        )
        self._write(
            root,
            "src_fatfs/diskio.c",
            b"DWORD get_fattime(void) {\r\n"
            b"\tyr =  (tstruct.year - EPOCH_YEAR) << 25;\r\n"
            b"}\r\n",
        )
        self._write(
            root,
            "src/mos_api.asm",
            b"\t\t\tJR\tNC, $F\t\t\t; Yes, so jump to next block\r\n",
        )
        self._write(
            root,
            "src/sd.asm",
            b"\t\tPUSH\t\tAF\t\t; Save res1 to be returned\r\n"
            b"\t\tCP\t\tA,SD_READY\r\n"
            b"\t\tJR\t\tNZ,$out3\r\n",
        )
        self._write(
            root,
            "src/vdp_protocol.asm",
            b"\t\t\tJR\tZ, vdp_protocol_state3\r\n",
        )
        self._write(root, "tracked.bin", b"\x00preserve\r\n\xff\n")
        self._write(root, "untracked.txt", b"must not be copied\n")
        subprocess.run(["git", "-C", os.fspath(root), "add", "--all"], check=True)
        subprocess.run(
            ["git", "-C", os.fspath(root), "reset", "--", "untracked.txt"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(root),
                "-c",
                "user.name=mos-agondev tests",
                "-c",
                "user.email=mos-agondev-tests@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-q",
                "-m",
                "fixture",
            ],
            check=True,
            env={
                **os.environ,
                "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
                "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
            },
        )

    @staticmethod
    def _run(script: Path, *arguments: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, os.fspath(script), *(os.fspath(arg) for arg in arguments)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_setup_creates_only_relative_links_and_accepts_exact_rerun(self) -> None:
        result = self._run(
            SETUP_SCRIPT,
            "--repo-root",
            self.repository,
            "--agondev",
            self.agondev,
            "--agon-mos",
            self.mos,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        agondev_link = self.repository / "toolchains" / "agondev"
        mos_link = self.repository / "upstream" / "agon-mos"
        self.assertTrue(agondev_link.is_symlink())
        self.assertTrue(mos_link.is_symlink())
        self.assertFalse(os.path.isabs(os.readlink(agondev_link)))
        self.assertFalse(os.path.isabs(os.readlink(mos_link)))
        self.assertEqual(agondev_link.resolve(), (self.agondev / "release").resolve())
        self.assertEqual(mos_link.resolve(), self.mos.resolve())
        self.assertEqual([item.name for item in agondev_link.parent.iterdir()], ["agondev"])
        self.assertEqual([item.name for item in mos_link.parent.iterdir()], ["agon-mos"])

        second = self._run(
            SETUP_SCRIPT,
            "--root",
            self.repository,
            "--agondev-source",
            self.agondev,
            "--mos-source",
            self.mos,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(agondev_link.resolve(), (self.agondev / "release").resolve())
        self.assertEqual(mos_link.resolve(), self.mos.resolve())

    def test_setup_defaults_to_project_local_dependency_directories(self) -> None:
        (self.repository / "agondev").symlink_to(
            self.agondev, target_is_directory=True
        )
        (self.repository / "agon-mos").symlink_to(
            self.mos, target_is_directory=True
        )

        result = self._run(SETUP_SCRIPT, "--repo-root", self.repository)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.repository / "toolchains/agondev").resolve(),
            (self.agondev / "release").resolve(),
        )
        self.assertEqual(
            (self.repository / "upstream/agon-mos").resolve(), self.mos.resolve()
        )

    def test_setup_preflights_both_destinations_before_creating_links(self) -> None:
        collision = self.repository / "upstream" / "agon-mos"
        collision.parent.mkdir()
        collision.mkdir()

        result = self._run(
            SETUP_SCRIPT,
            "--root",
            self.repository,
            "--agondev",
            self.agondev,
            "--agon-mos",
            self.mos,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing to replace existing path", result.stderr)
        self.assertFalse((self.repository / "toolchains" / "agondev").exists())
        self.assertTrue(collision.is_dir())

    def test_prepare_copies_only_tracked_bytes_and_validates_port_edits(self) -> None:
        tracked = subprocess.run(
            ["git", "-C", os.fspath(self.mos), "ls-files", "-z"],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout.split(b"\0")
        source_snapshot = {
            os.fsdecode(name): (self.mos / os.fsdecode(name)).read_bytes()
            for name in tracked
            if name
        }
        destination = self.repository / "projects" / "mos-port" / "generated-worktree"

        result = self._run(
            PREPARE_SCRIPT,
            "--repo-root",
            self.repository,
            "--upstream",
            self.mos,
            "--destination",
            destination,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(destination.is_dir())
        self.assertFalse((destination / ".git").exists())
        self.assertFalse((destination / "untracked.txt").exists())
        self.assertEqual((destination / "tracked.bin").read_bytes(), b"\x00preserve\r\n\xff\n")

        metadata = json.loads(
            (destination / PREPARATION_METADATA).read_text(encoding="utf-8")
        )
        head = subprocess.run(
            ["git", "-C", os.fspath(self.mos), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        self.assertEqual(metadata["schema"], 1)
        self.assertEqual(
            metadata["source"], {"head": head, "tracked_dirty": False}
        )
        entries = {entry["path"]: entry for entry in metadata["files"]}
        self.assertEqual(set(entries), set(source_snapshot))
        self.assertNotIn(PREPARATION_METADATA, entries)
        self.assertEqual(
            entries["main.c"]["sha256"],
            hashlib.sha256((destination / "main.c").read_bytes()).hexdigest(),
        )
        self.assertEqual(entries["tracked.bin"]["executable_bits"], "000")

        defines = (destination / "src" / "defines.h").read_bytes()
        self.assertEqual(defines.count(b"extern unsigned char "), 6)
        self.assertNotIn(b"extern void ", defines)
        self.assertIn(
            b"extern unsigned char _heapbot[];",
            (destination / "main.c").read_bytes(),
        )
        main = (destination / "main.c").read_bytes()
        self.assertIn(b"#include <ez80.h>\r\n", main)
        self.assertIn(b"#include <ctype.h>\r\n", main)
        self.assertIn(b"#include <string.h>\r\n", main)
        self.assertNotIn(b"#include <eZ80.h>", main)
        self.assertNotIn(b"#include <CTYPE.h>", main)
        self.assertNotIn(b"#include <String.h>", main)
        self.assertIn(
            b'__asm__ volatile ("ld a,r" : "=a"(value) : : "cc");\r\n'
            b"\treturn value;",
            main,
        )
        self.assertIn(b"#ifdef AGONDEV", main)
        self.assertIn(
            b"extern unsigned char sysvars[];",
            (destination / "src" / "mos.c").read_bytes(),
        )
        for relative in ("src/mos.c", "src/mos_editor.c", "src/timer.c", "src/uart.c"):
            source = (destination / relative).read_bytes()
            self.assertIn(b"#include <ez80.h>", source)
            self.assertNotIn(b"#include <eZ80.h>", source)
        clock = (destination / "src" / "clock.h").read_bytes()
        self.assertIn(b"#include <defines.h>\r\n\r\n#define EPOCH_YEAR", clock)
        self.assertNotIn(b"\n", clock.replace(b"\r\n", b""))
        self.assertIn(
            b"(DWORD)(tstruct.year - EPOCH_YEAR) << 25",
            (destination / "src_fatfs" / "diskio.c").read_bytes(),
        )
        self.assertIn(
            b"JP\tNC, $F",
            (destination / "src" / "mos_api.asm").read_bytes(),
        )
        self.assertIn(
            b"JP\t\tNZ,$out3",
            (destination / "src" / "sd.asm").read_bytes(),
        )
        self.assertIn(
            b"JP\tZ, vdp_protocol_state3",
            (destination / "src" / "vdp_protocol.asm").read_bytes(),
        )

        for relative_name, original in source_snapshot.items():
            self.assertEqual((self.mos / relative_name).read_bytes(), original)

        second = self._run(
            PREPARE_SCRIPT,
            "--root",
            self.repository,
            "--source",
            self.mos,
            "--destination",
            destination,
        )
        self.assertEqual(second.returncode, 2)
        self.assertIn("refusing to replace existing destination", second.stderr)

    def test_prepare_records_tracked_dirty_state_but_ignores_untracked_files(self) -> None:
        (self.mos / "tracked.bin").write_bytes(b"tracked dirty bytes\n")
        (self.mos / "another-untracked.txt").write_text(
            "ignored\n", encoding="utf-8"
        )
        destination = self.repository / "projects" / "mos-port" / "dirty-worktree"

        result = self._run(
            PREPARE_SCRIPT,
            "--root",
            self.repository,
            "--source",
            self.mos,
            "--destination",
            destination,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = json.loads(
            (destination / PREPARATION_METADATA).read_text(encoding="utf-8")
        )
        self.assertTrue(metadata["source"]["tracked_dirty"])
        self.assertFalse((destination / "untracked.txt").exists())
        self.assertFalse((destination / "another-untracked.txt").exists())
        tracked = next(
            entry for entry in metadata["files"] if entry["path"] == "tracked.bin"
        )
        self.assertEqual(
            tracked["sha256"],
            hashlib.sha256(b"tracked dirty bytes\n").hexdigest(),
        )

    def test_prepare_rejects_unvalidated_source_before_destination_creation(self) -> None:
        diskio = self.mos / "src_fatfs" / "diskio.c"
        diskio.write_bytes(b"DWORD get_fattime(void) { return 0; }\r\n")
        destination = self.repository / "projects" / "mos-port" / "bad-worktree"

        result = self._run(
            PREPARE_SCRIPT,
            "--root",
            self.repository,
            "--source",
            self.mos,
            "--destination",
            destination,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("DWORD shift", result.stderr)
        self.assertFalse(os.path.lexists(destination))

    def test_prepare_check_accepts_exact_tree_without_changing_it(self) -> None:
        destination = self.repository / "projects" / "mos-port" / "checked-worktree"
        prepared = self._run(
            PREPARE_SCRIPT,
            "--root",
            self.repository,
            "--source",
            self.mos,
            "--destination",
            destination,
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        before = {
            path.relative_to(destination).as_posix(): (
                path.read_bytes(),
                path.stat().st_mode,
            )
            for path in destination.rglob("*")
            if path.is_file()
        }

        checked = self._run(
            PREPARE_SCRIPT,
            "--root",
            self.repository,
            "--source",
            self.mos,
            "--destination",
            destination,
            "--check",
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("verified", checked.stdout)
        after = {
            path.relative_to(destination).as_posix(): (
                path.read_bytes(),
                path.stat().st_mode,
            )
            for path in destination.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_prepare_check_rejects_content_extra_missing_mode_and_symlink_drift(self) -> None:
        mutations = (
            "content",
            "extra",
            "missing",
            "mode",
            "symlink",
            "metadata-content",
            "metadata-missing",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                destination = (
                    self.repository / "projects" / "mos-port" / f"drift-{mutation}"
                )
                prepared = self._run(
                    PREPARE_SCRIPT,
                    "--root",
                    self.repository,
                    "--source",
                    self.mos,
                    "--destination",
                    destination,
                )
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                if mutation == "content":
                    (destination / "tracked.bin").write_bytes(b"drift\n")
                elif mutation == "extra":
                    (destination / "extra.txt").write_text("extra\n", encoding="utf-8")
                elif mutation == "missing":
                    (destination / "tracked.bin").unlink()
                elif mutation == "mode":
                    (destination / "tracked.bin").chmod(0o744)
                elif mutation == "symlink":
                    target = destination / "tracked.bin"
                    target.unlink()
                    target.symlink_to(self.mos / "tracked.bin")
                elif mutation == "metadata-content":
                    (destination / PREPARATION_METADATA).write_text(
                        "{}\n", encoding="utf-8"
                    )
                else:
                    (destination / PREPARATION_METADATA).unlink()

                checked = self._run(
                    PREPARE_SCRIPT,
                    "--root",
                    self.repository,
                    "--source",
                    self.mos,
                    "--destination",
                    destination,
                    "--check",
                )
                self.assertEqual(checked.returncode, 2)
                self.assertIn("destination", checked.stderr)


if __name__ == "__main__":
    unittest.main()
