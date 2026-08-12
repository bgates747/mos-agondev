from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import setup_emulator  # noqa: E402
import verify_emulator  # noqa: E402


class EmulatorScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp = Path(self.temporary_directory.name)
        self.fab_root = self.temp / "fab"
        self.profile = self.temp / "profile"
        self.fake_log = self.temp / "emulator.log"
        self._create_fake_fab()

    def _create_fake_fab(self) -> None:
        executable = self.fab_root / "fab-agon-emulator"
        firmware = self.fab_root / "firmware"
        sdcard = self.fab_root / "sdcard"
        shared_bin = sdcard / "bin"
        shared_mos = sdcard / "mos"
        firmware.mkdir(parents=True)
        shared_bin.mkdir(parents=True)
        shared_mos.mkdir(parents=True)

        executable.write_text(
            "#!/bin/sh\n"
            "{\n"
            "  printf 'cwd=%s\\n' \"$PWD\"\n"
            "  printf 'video=%s\\n' \"$SDL_VIDEODRIVER\"\n"
            "  for arg in \"$@\"; do printf 'arg=%s\\n' \"$arg\"; done\n"
            "} > \"$FAKE_EMULATOR_LOG\"\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        (firmware / "mos_platform.bin").write_bytes(b"stock-platform-mos")
        (firmware / "mos_platform.map").write_text(
            "EXTERNAL DEFINITIONS:\n", encoding="ascii"
        )
        (firmware / "vdp_platform.so").write_bytes(b"stock-platform-vdp")
        (shared_bin / "alpha.bin").write_bytes(b"alpha")
        (shared_bin / "beta.bin").write_bytes(b"beta")
        (shared_mos / "flash.bin").write_bytes(b"flash")
        (sdcard / "MOS.bin").write_bytes(b"update-mos")
        (sdcard / "firmware.bin").write_bytes(b"update-vdp")

    def test_setup_creates_stock_profile_and_verifies_it(self) -> None:
        profile = setup_emulator.setup_profile(self.profile, self.fab_root)

        self.assertEqual(profile, self.profile)
        self.assertTrue((profile / "fab-agon-emulator").is_symlink())
        self.assertEqual(
            (profile / "fab-agon-emulator").resolve(),
            (self.fab_root / "fab-agon-emulator").resolve(),
        )
        self.assertTrue((profile / "firmware").is_symlink())
        self.assertTrue((profile / "sdcard/mos").is_symlink())
        self.assertTrue((profile / "sdcard/MOS.bin").is_symlink())
        self.assertTrue((profile / "sdcard/firmware.bin").is_symlink())
        self.assertTrue((profile / "sdcard/bin").is_dir())
        self.assertFalse((profile / "sdcard/bin").is_symlink())
        self.assertTrue((profile / "sdcard/agondev").is_dir())
        self.assertFalse((profile / "sdcard/agondev").is_symlink())
        self.assertEqual(
            (profile / "sdcard/autoexec.txt").read_bytes(),
            b"SET KEYBOARD 1\r\n",
        )
        for name in ("alpha.bin", "beta.bin"):
            destination = profile / "sdcard/bin" / name
            self.assertTrue(destination.is_symlink())
            self.assertEqual(
                destination.resolve(), (self.fab_root / "sdcard/bin" / name).resolve()
            )

        result = verify_emulator.verify_profile(profile, self.fab_root)
        self.assertEqual(result.local_bin_overrides, ())
        self.assertEqual(set(result.hashes), {"fab", "mos_platform", "vdp_platform"})

    def test_refresh_repairs_links_and_preserves_real_local_files(self) -> None:
        setup_emulator.setup_profile(self.profile, self.fab_root)
        executable_link = self.profile / "fab-agon-emulator"
        executable_link.unlink()
        executable_link.symlink_to(self.temp / "wrong-emulator")

        alpha = self.profile / "sdcard/bin/alpha.bin"
        alpha.unlink()
        alpha.write_bytes(b"local-alpha")
        local_artifact = self.profile / "sdcard/agondev/probe.bin"
        local_artifact.write_bytes(b"probe")
        autoexec = self.profile / "sdcard/autoexec.txt"
        autoexec.write_bytes(b"REM user controlled\r\n")

        setup_emulator.setup_profile(self.profile, self.fab_root)

        self.assertEqual(
            executable_link.resolve(),
            (self.fab_root / "fab-agon-emulator").resolve(),
        )
        self.assertFalse(alpha.is_symlink())
        self.assertEqual(alpha.read_bytes(), b"local-alpha")
        self.assertEqual(local_artifact.read_bytes(), b"probe")
        self.assertEqual(autoexec.read_bytes(), b"REM user controlled\r\n")
        result = verify_emulator.verify_profile(self.profile, self.fab_root)
        self.assertEqual(result.local_bin_overrides, (alpha,))

    def test_setup_converts_only_a_symlinked_bin_overlay(self) -> None:
        (self.profile / "sdcard").mkdir(parents=True)
        (self.profile / "sdcard/bin").symlink_to(self.fab_root / "sdcard/bin")

        setup_emulator.setup_profile(self.profile, self.fab_root)

        profile_bin = self.profile / "sdcard/bin"
        self.assertTrue(profile_bin.is_dir())
        self.assertFalse(profile_bin.is_symlink())
        self.assertTrue((profile_bin / "alpha.bin").is_symlink())

    def test_setup_refuses_and_preserves_real_managed_path(self) -> None:
        self.profile.mkdir()
        managed_path = self.profile / "fab-agon-emulator"
        managed_path.write_bytes(b"local executable")

        with self.assertRaises(setup_emulator.SetupError):
            setup_emulator.setup_profile(self.profile, self.fab_root)

        self.assertEqual(managed_path.read_bytes(), b"local executable")
        self.assertFalse((self.profile / "firmware").exists())
        self.assertFalse((self.profile / "sdcard").exists())

    def test_missing_upstream_input_fails_before_profile_creation(self) -> None:
        (self.fab_root / "firmware/vdp_platform.so").unlink()

        with self.assertRaises(setup_emulator.SetupError):
            setup_emulator.setup_profile(self.profile, self.fab_root)

        self.assertFalse(self.profile.exists())

    def test_verification_reports_broken_link_without_repairing_it(self) -> None:
        setup_emulator.setup_profile(self.profile, self.fab_root)
        update_link = self.profile / "sdcard/MOS.bin"
        update_link.unlink()
        raw_target = "../../../missing/MOS.bin"
        update_link.symlink_to(raw_target)

        with self.assertRaises(verify_emulator.VerificationError):
            verify_emulator.verify_profile(self.profile, self.fab_root)

        self.assertTrue(update_link.is_symlink())
        self.assertEqual(os.readlink(update_link), raw_target)

    def test_cli_path_overrides(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            setup_status = setup_emulator.main(
                ["--profile", str(self.profile), "--fab-root", str(self.fab_root)]
            )
            verify_status = verify_emulator.main(
                [
                    "--profile",
                    str(self.profile),
                    "--fab-root",
                    str(self.fab_root),
                    "--quiet",
                ]
            )

        self.assertEqual(setup_status, 0, stderr.getvalue())
        self.assertEqual(verify_status, 0, stderr.getvalue())
        self.assertIn(str(self.profile), stdout.getvalue())

    def test_launcher_uses_explicit_stock_runtime_and_local_sdcard(self) -> None:
        setup_emulator.setup_profile(self.profile, self.fab_root)
        environment = os.environ.copy()
        environment.update(
            {
                "MOS_AGONDEV_PYTHON": sys.executable,
                "MOS_AGONDEV_EMULATOR_PROFILE": str(self.profile),
                "MOS_AGONDEV_FAB_ROOT": str(self.fab_root),
                "FAKE_EMULATOR_LOG": str(self.fake_log),
            }
        )

        completed = subprocess.run(
            ["bash", str(SCRIPTS / "run_emulator.sh"), "--fullscreen"],
            cwd=self.temp,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            self.fake_log.read_text(encoding="utf-8").splitlines(),
            [
                f"cwd={self.profile}",
                "video=wayland",
                "arg=--renderer",
                "arg=sw",
                "arg=--firmware",
                "arg=platform",
                "arg=--sdcard",
                "arg=./sdcard",
                "arg=--verbose",
                "arg=-z",
                "arg=--fullscreen",
            ],
        )

    def test_launcher_rejects_runtime_identity_overrides(self) -> None:
        setup_emulator.setup_profile(self.profile, self.fab_root)
        environment = os.environ.copy()
        environment.update(
            {
                "MOS_AGONDEV_PYTHON": sys.executable,
                "MOS_AGONDEV_EMULATOR_PROFILE": str(self.profile),
                "MOS_AGONDEV_FAB_ROOT": str(self.fab_root),
                "FAKE_EMULATOR_LOG": str(self.fake_log),
            }
        )

        completed = subprocess.run(
            ["bash", str(SCRIPTS / "run_emulator.sh"), "--mos", "custom.bin"],
            cwd=self.temp,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("manages this option: --mos", completed.stderr)
        self.assertFalse(self.fake_log.exists())


if __name__ == "__main__":
    unittest.main()
