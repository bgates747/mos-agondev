#!/usr/bin/env python3
"""Verify or explicitly record the reviewed binary-comparison evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parents[1]
DEFAULT_REPORT = PROJECT / "artifacts" / "report" / "report.json"
DEFAULT_EVIDENCE = ROOT / "evidence" / "binary-compare-v3.0.2.json"


class VerificationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise VerificationError(f"JSON input is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"expected a JSON object in {path}")
    return value


def evidence_view(report: dict[str, Any]) -> dict[str, Any]:
    source = report["candidate"]["source"]
    summary = report["summary"]
    if summary["high_priority_review_entries"]:
        raise VerificationError("comparison still has high-priority unexplained assembly")
    preparation_paths = [item["path"] for item in report["preparation_changes"]]
    return {
        "schema": 1,
        "reference": report["reference"],
        "candidate": {
            "source": source,
            "binary": report["candidate"]["binary"],
            "elf_sha256": report["candidate"]["elf_sha256"],
            "map_sha256": report["candidate"]["map_sha256"],
            "artifact_manifest_sha256": report["candidate"]["artifact_manifest_sha256"],
        },
        "source_divergence": report["source_divergence"],
        "preparation_paths": preparation_paths,
        "raw_image_difference": report["raw_image_difference"],
        "summary": summary,
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise VerificationError(f"evidence output may not be a symlink: {path}")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument(
        "--record",
        action="store_true",
        help="replace the reviewed evidence explicitly instead of checking it",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        actual = evidence_view(load_json(args.report.resolve()))
        evidence = args.evidence.resolve()
        if args.record:
            write_json(evidence, actual)
            print(f"binary comparison evidence recorded: {evidence}")
            return 0
        expected = load_json(evidence)
        if actual != expected:
            raise VerificationError(
                "binary comparison differs from reviewed evidence; inspect report.md and "
                "review-queue.json, then use --record only after review"
            )
        print(
            "binary comparison evidence verified: "
            f"{actual['summary']['assembly_slices']} complete assembly slices"
        )
        return 0
    except (KeyError, OSError, VerificationError) as exc:
        print(f"report verification error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
