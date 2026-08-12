from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PortablePathTests(unittest.TestCase):
    def test_tracked_text_has_no_machine_specific_paths(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        )
        forbidden = re.compile(
            "|".join(
                (
                    "/" + "home/",
                    "/" + "Users/",
                    "/" + "tmp/",
                    "~" + "/",
                    r"\$\{?" + "HOME" + r"\}?",
                    "Path." + "home" + r"\(",
                    r"\b[A-Za-z]:\\" + "Users" + r"\\",
                )
            )
        )
        violations: list[str] = []
        for raw_name in result.stdout.split(b"\0"):
            if not raw_name:
                continue
            relative = Path(raw_name.decode("utf-8"))
            path = ROOT / relative
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, IsADirectoryError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if forbidden.search(line):
                    violations.append(f"{relative}:{line_number}: {line.strip()}")
        self.assertEqual([], violations, "machine-specific paths found")


if __name__ == "__main__":
    unittest.main()
