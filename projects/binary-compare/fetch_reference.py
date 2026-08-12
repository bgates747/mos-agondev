#!/usr/bin/env python3
"""Fetch or import the pinned official MOS release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = PROJECT / "reference" / "v3.0.2.json"
DEFAULT_OUTPUT = PROJECT / "artifacts" / "reference" / "v3.0.2"
LATEST_API = "https://api.github.com/repos/AgonPlatform/agon-mos/releases/latest"
TAG_API = "https://api.github.com/repos/AgonPlatform/agon-mos/git/ref/tags/{tag}"


class ReferenceError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReferenceError(f"cannot read reference manifest {path}: {exc}") from exc
    if data.get("schema") != 1 or not isinstance(data.get("assets"), dict):
        raise ReferenceError("reference manifest must use schema 1 and contain assets")
    release = data.get("release")
    if not isinstance(release, dict) or not isinstance(release.get("tag"), str):
        raise ReferenceError("reference manifest has no release tag")
    for name, entry in data["assets"].items():
        if name not in {"MOS.bin", "MOS.hex", "MOS.map"}:
            raise ReferenceError(f"unexpected reference asset: {name!r}")
        if not isinstance(entry, dict):
            raise ReferenceError(f"invalid reference asset entry: {name}")
        digest = entry.get("sha256")
        size = entry.get("size")
        url = entry.get("url")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ReferenceError(f"invalid SHA-256 for {name}")
        if not isinstance(size, int) or size <= 0:
            raise ReferenceError(f"invalid size for {name}")
        expected_url = (
            "https://github.com/AgonPlatform/agon-mos/releases/download/"
            f"{release['tag']}/{name}"
        )
        if url != expected_url:
            raise ReferenceError(f"unexpected official URL for {name}: {url!r}")
    if set(data["assets"]) != {"MOS.bin", "MOS.hex", "MOS.map"}:
        raise ReferenceError("reference manifest must pin MOS.bin, MOS.hex, and MOS.map")
    return data


def verify_asset(path: Path, name: str, entry: dict[str, Any]) -> None:
    if path.is_symlink() or not path.is_file():
        raise ReferenceError(f"reference asset is not a regular file: {path}")
    actual_size = path.stat().st_size
    if actual_size != entry["size"]:
        raise ReferenceError(
            f"{name} size mismatch: expected {entry['size']}, got {actual_size}"
        )
    actual_hash = sha256_file(path)
    if actual_hash != entry["sha256"]:
        raise ReferenceError(
            f"{name} SHA-256 mismatch: expected {entry['sha256']}, got {actual_hash}"
        )


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mos-agondev-reference-fetch/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            value = json.load(response)
    except json.JSONDecodeError as exc:
        raise ReferenceError(f"GitHub API returned invalid JSON for {url}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReferenceError(f"GitHub API returned a non-object for {url}")
    return value


def validate_latest_release(
    manifest: dict[str, Any], release: dict[str, Any], tag_commit: str
) -> None:
    expected = manifest["release"]
    checks = {
        "tag_name": expected["tag"],
        "name": expected["name"],
        "published_at": expected["published_at"],
        "html_url": expected["url"],
    }
    for field, value in checks.items():
        if release.get(field) != value:
            raise ReferenceError(
                f"latest official release {field} changed: expected {value!r}, "
                f"got {release.get(field)!r}"
            )
    if tag_commit != expected["commit"]:
        raise ReferenceError(
            f"release tag commit changed: expected {expected['commit']}, got {tag_commit}"
        )
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ReferenceError("latest official release has no asset list")
    actual = {
        item.get("name"): {
            "size": item.get("size"),
            "url": item.get("browser_download_url"),
        }
        for item in assets
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    expected_assets = {
        name: {"size": entry["size"], "url": entry["url"]}
        for name, entry in manifest["assets"].items()
    }
    if actual != expected_assets:
        raise ReferenceError(
            f"latest official release asset inventory changed: {actual!r}"
        )


def verify_latest_release(manifest: dict[str, Any]) -> None:
    release = fetch_json(LATEST_API)
    tag = manifest["release"]["tag"]
    reference = fetch_json(TAG_API.format(tag=tag))
    git_object = reference.get("object")
    if not isinstance(git_object, dict):
        raise ReferenceError("GitHub tag reference has no object")
    object_type = git_object.get("type")
    object_sha = git_object.get("sha")
    if object_type == "tag":
        annotated = fetch_json(
            f"https://api.github.com/repos/AgonPlatform/agon-mos/git/tags/{object_sha}"
        )
        git_object = annotated.get("object")
        if not isinstance(git_object, dict):
            raise ReferenceError("annotated GitHub tag has no target object")
        object_type = git_object.get("type")
        object_sha = git_object.get("sha")
    if object_type != "commit" or not isinstance(object_sha, str):
        raise ReferenceError("release tag does not resolve to a commit")
    validate_latest_release(manifest, release, object_sha)


def materialize_asset(
    name: str,
    entry: dict[str, Any],
    output: Path,
    source_dir: Path | None,
) -> None:
    destination = output / name
    if destination.exists() or destination.is_symlink():
        verify_asset(destination, name, entry)
        return
    if source_dir is not None:
        source = source_dir / name
        verify_asset(source, name, entry)
    else:
        source = None

    fd, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=output)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        if source is not None:
            shutil.copyfile(source, temporary)
        else:
            request = urllib.request.Request(
                entry["url"], headers={"User-Agent": "mos-agondev-reference-fetch/1"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                with temporary.open("wb") as stream:
                    shutil.copyfileobj(response, stream)
        verify_asset(temporary, name, entry)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="import already-downloaded official assets instead of using the network",
    )
    parser.add_argument(
        "--check", action="store_true", help="verify the existing artifact cache only"
    )
    parser.add_argument(
        "--verify-latest",
        action="store_true",
        help="ask GitHub whether the pinned release is still the newest published release",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = load_manifest(args.manifest.resolve())
        if args.verify_latest:
            verify_latest_release(manifest)
        output = args.output.resolve()
        if output.is_symlink():
            raise ReferenceError(f"output directory may not be a symlink: {output}")
        if args.check:
            if not output.is_dir():
                raise ReferenceError(f"reference cache does not exist: {output}")
        else:
            output.mkdir(parents=True, exist_ok=True)
            if not output.is_dir() or output.is_symlink():
                raise ReferenceError(f"unsafe output directory: {output}")
        source_dir = args.source_dir.resolve() if args.source_dir else None
        if source_dir is not None and (not source_dir.is_dir() or source_dir.is_symlink()):
            raise ReferenceError(f"source directory is not a real directory: {source_dir}")
        for name in sorted(manifest["assets"]):
            entry = manifest["assets"][name]
            if args.check:
                verify_asset(output / name, name, entry)
            else:
                materialize_asset(name, entry, output, source_dir)
        print(
            f"official MOS {manifest['release']['tag']} reference verified: "
            f"{len(manifest['assets'])} artifacts"
        )
        return 0
    except (OSError, ReferenceError, urllib.error.URLError) as exc:
        print(f"reference error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
