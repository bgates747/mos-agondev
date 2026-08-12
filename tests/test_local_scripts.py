from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = REPOSITORY_ROOT / "scripts" / "setup_local.py"
PREPARE_SCRIPT = REPOSITORY_ROOT / "scripts" / "prepare_mos_worktree.py"

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
            b"int quickrand(void) { return 0; }\r\n"
            b"extern void _heapbot[];\r\n",
        )
        self._write(root, "src/mos.c", b"extern void sysvars[];\r\n")
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
        self._write(root, "tracked.bin", b"\x00preserve\r\n\xff\n")
        self._write(root, "untracked.txt", b"must not be copied\n")
        subprocess.run(["git", "-C", os.fspath(root), "add", "--all"], check=True)
        subprocess.run(
            ["git", "-C", os.fspath(root), "reset", "--", "untracked.txt"],
            check=True,
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

    def test_prepare_copies_only_tracked_bytes_and_validates_five_edits(self) -> None:
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

        defines = (destination / "src" / "defines.h").read_bytes()
        self.assertEqual(defines.count(b"extern unsigned char "), 6)
        self.assertNotIn(b"extern void ", defines)
        self.assertIn(
            b"extern unsigned char _heapbot[];",
            (destination / "main.c").read_bytes(),
        )
        self.assertIn(
            b"extern unsigned char sysvars[];",
            (destination / "src" / "mos.c").read_bytes(),
        )
        clock = (destination / "src" / "clock.h").read_bytes()
        self.assertIn(b"#include <defines.h>\r\n\r\n#define EPOCH_YEAR", clock)
        self.assertNotIn(b"\n", clock.replace(b"\r\n", b""))
        self.assertIn(
            b"(DWORD)(tstruct.year - EPOCH_YEAR) << 25",
            (destination / "src_fatfs" / "diskio.c").read_bytes(),
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


if __name__ == "__main__":
    unittest.main()
