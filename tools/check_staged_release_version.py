#!/usr/bin/env python3
"""Require a higher HASC version when release-relevant files are staged.

The check reads only the local Git index and the preceding local commit. It
does not contact Home Assistant, a home, devices, or the internet.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIRECTORY = PurePosixPath("custom_components/hausman_hub")
MANIFEST_PATH = INTEGRATION_DIRECTORY / "manifest.json"
HACS_METADATA_PATH = PurePosixPath("hacs.json")
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class ReleaseVersionCheckError(RuntimeError):
    """Explain why the local Git-only version check could not complete."""


def main() -> int:
    """Check the staged release boundary and report a plain result."""

    try:
        staged_paths = staged_file_paths(REPOSITORY_ROOT)
        if not has_release_relevant_change(staged_paths):
            print("No integration or HACS metadata change is staged.")
            return 0

        previous = manifest_version(REPOSITORY_ROOT, f"HEAD:{MANIFEST_PATH}")
        staged = manifest_version(REPOSITORY_ROOT, f":{MANIFEST_PATH}")
    except ReleaseVersionCheckError as exc:
        print(f"Staged release version check could not run: {exc}", file=sys.stderr)
        return 2

    finding = version_change_finding(previous, staged)
    if finding is not None:
        print(f"Staged release version check failed: {finding}", file=sys.stderr)
        return 1

    print(f"Staged release version increased from {previous} to {staged}.")
    return 0


def has_release_relevant_change(paths: Iterable[PurePosixPath]) -> bool:
    """Return whether a staged path needs an HACS-visible version increase."""

    return any(
        path == HACS_METADATA_PATH or path.is_relative_to(INTEGRATION_DIRECTORY)
        for path in paths
    )


def version_change_finding(previous: str, staged: str) -> str | None:
    """Require the staged manifest version to be higher than the prior version."""

    previous_parts = parse_release_version(previous)
    staged_parts = parse_release_version(staged)
    if staged_parts <= previous_parts:
        return (
            f"integration or HACS metadata changed, but manifest version must increase "
            f"from {previous}; staged version is {staged}"
        )
    return None


def parse_release_version(value: str) -> tuple[int, int, int]:
    """Parse the simple three-number version format used by this integration."""

    matched = VERSION_PATTERN.fullmatch(value)
    if matched is None:
        raise ReleaseVersionCheckError(
            f"manifest version must use three non-negative numbers, got {value!r}"
        )
    return tuple(int(part) for part in matched.groups())


def staged_file_paths(root: Path) -> tuple[PurePosixPath, ...]:
    """Read only added or changed paths from the local Git staging area."""

    completed = run_git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMRDT", "-z")
    paths: list[PurePosixPath] = []
    for raw_path in completed.stdout.split(b"\0"):
        if raw_path:
            paths.append(checked_relative_path(raw_path))
    return tuple(paths)


def manifest_version(root: Path, revision: str) -> str:
    """Read one manifest version from a local Git revision without using files."""

    completed = run_git(root, "show", revision)
    try:
        manifest = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseVersionCheckError(f"cannot read manifest at {revision}") from exc
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str):
        raise ReleaseVersionCheckError(f"manifest at {revision} has no string version")
    parse_release_version(version)
    return version


def checked_relative_path(raw_path: bytes) -> PurePosixPath:
    """Reject malformed Git output before comparing repository-relative paths."""

    try:
        path = PurePosixPath(raw_path.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ReleaseVersionCheckError("Git returned a non-UTF-8 path") from exc
    if path.is_absolute() or ".." in path.parts:
        raise ReleaseVersionCheckError(f"Git returned an unsafe path: {path}")
    return path


def run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """Run a local Git read command without a shell or network access."""

    try:
        return subprocess.run(
            ("git", *arguments),
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseVersionCheckError(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
