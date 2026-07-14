#!/usr/bin/env python3
"""Reject accidentally publishable Home Assistant runtime data and credentials.

The check reads only this Git working copy or its staged Git files.  It never
contacts Home Assistant, Node-RED, or any other network service.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DIRECTORY_NAMES = frozenset(
    {".storage", "credentials", "flow-backups", "node-red", "node-red-data"}
)
FORBIDDEN_RUNTIME_FILE_NAMES = frozenset(
    {"automations.yaml", "configuration.yaml", "scenes.yaml", "scripts.yaml"}
)
FLOW_FILE_NAME_PATTERN = re.compile(r"(?:^|[-_.])flows?(?:[-_.]|$)", re.IGNORECASE)
PRIVATE_KEY_PATTERN = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
ASSIGNED_SECRET_PATTERN = re.compile(
    rb"(?im)^\s*(?:access[_-]?token|api[_-]?key|password|secret)\s*[:=]\s*"
    rb"[\"']?[A-Za-z0-9._~+/=-]{20,}"
)
BEARER_TOKEN_PATTERN = re.compile(
    rb"(?im)^\s*authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{20,}"
)
HOSTED_TOKEN_PATTERN = re.compile(rb"\b(?:ghp_|gho_|github_pat_|glpat-)[A-Za-z0-9_-]{16,}\b")
JSON_WEB_TOKEN_PATTERN = re.compile(
    rb"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)
CONTENT_PATTERNS = (
    ("private key", PRIVATE_KEY_PATTERN),
    ("assigned secret", ASSIGNED_SECRET_PATTERN),
    ("bearer token", BEARER_TOKEN_PATTERN),
    ("hosted-service token", HOSTED_TOKEN_PATTERN),
    ("JSON web token", JSON_WEB_TOKEN_PATTERN),
)


@dataclass(frozen=True, slots=True)
class RepositoryFile:
    """One repository path and its bytes, without interpreting home data."""

    path: PurePosixPath
    content: bytes


def main(argv: list[str] | None = None) -> int:
    """Check tracked files, or exactly the files waiting for the next commit."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="check only files staged for the next Git commit",
    )
    args = parser.parse_args(argv)

    try:
        files = staged_files(REPOSITORY_ROOT) if args.staged else tracked_files(REPOSITORY_ROOT)
    except RepositoryCheckError as exc:
        print(f"Repository safety check could not run: {exc}", file=sys.stderr)
        return 2

    findings = find_boundary_violations(files)
    if findings:
        print("Repository safety check failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    scope = "staged files" if args.staged else "tracked files"
    print(f"Repository safety check passed for {scope}.")
    return 0


class RepositoryCheckError(RuntimeError):
    """Explain why the local Git-only inspection could not complete."""


def tracked_files(root: Path) -> tuple[RepositoryFile, ...]:
    """Read every tracked file from Git's index, never from the working tree.

    Reading the indexed blob rather than ``Path.read_bytes`` is deliberate:
    a tracked symbolic link could otherwise make this safety check read a file
    outside the repository.
    """

    paths = git_file_list(root, "ls-files")
    return git_index_files(root, paths)


def staged_files(root: Path) -> tuple[RepositoryFile, ...]:
    """Read exactly the added or changed files from Git's staging area."""

    paths = git_file_list(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return git_index_files(root, paths)


def git_index_files(
    root: Path,
    paths: Iterable[PurePosixPath],
) -> tuple[RepositoryFile, ...]:
    """Read safe relative paths from the Git index without following links."""

    files: list[RepositoryFile] = []
    for relative_path in paths:
        result = run_git(root, "show", f":{relative_path.as_posix()}")
        files.append(RepositoryFile(relative_path, result.stdout))
    return tuple(files)


def git_file_list(root: Path, *arguments: str) -> tuple[PurePosixPath, ...]:
    """Return a NUL-delimited Git file list as safe relative paths."""

    result = run_git(root, *arguments, "-z")
    paths = tuple(
        checked_relative_path(raw_path)
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    )
    return paths


def run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    """Run one local Git read command without a shell or network access."""

    try:
        return subprocess.run(
            ("git", *arguments),
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RepositoryCheckError(str(exc)) from exc


def checked_relative_path(raw_path: bytes) -> PurePosixPath:
    """Reject malformed Git output before using it as a local file path."""

    try:
        path = PurePosixPath(raw_path.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise RepositoryCheckError("Git returned a non-UTF-8 path") from exc
    if path.is_absolute() or ".." in path.parts:
        raise RepositoryCheckError(f"Git returned an unsafe path: {path}")
    return path


def find_boundary_violations(files: Iterable[RepositoryFile]) -> tuple[str, ...]:
    """Return deterministic safety findings without changing any repository file."""

    findings: list[str] = []
    for file in files:
        path_finding = forbidden_path_finding(file.path)
        if path_finding is not None:
            findings.append(path_finding)
        findings.extend(content_findings(file))
    return tuple(sorted(findings))


def forbidden_path_finding(path: PurePosixPath) -> str | None:
    """Reject known runtime, backup, and credential file names."""

    name = path.name.lower()
    if any(part.lower() in FORBIDDEN_DIRECTORY_NAMES for part in path.parts[:-1]):
        return f"{path}: forbidden runtime or credential directory"
    if (
        name in FORBIDDEN_RUNTIME_FILE_NAMES
        or name == ".env"
        or name.startswith(".env.")
        or name == "secrets.yaml"
        or name.startswith("secrets.")
        or name.endswith((".key", ".pem", ".token", ".bak", ".backup"))
        or name.startswith("config_entry-")
    ):
        return f"{path}: forbidden credential, configuration, or backup file name"
    if path.suffix.lower() == ".json" and FLOW_FILE_NAME_PATTERN.search(name):
        return f"{path}: forbidden Node-RED flow or flow backup file name"
    return None


def content_findings(file: RepositoryFile) -> tuple[str, ...]:
    """Find credential-shaped data without decoding binary project assets."""

    if b"\0" in file.content:
        return ()
    findings: list[str] = []
    for label, pattern in CONTENT_PATTERNS:
        matched = pattern.search(file.content)
        if matched is not None:
            line_number = file.content.count(b"\n", 0, matched.start()) + 1
            findings.append(f"{file.path}:{line_number}: possible {label}")
    return tuple(findings)


if __name__ == "__main__":
    raise SystemExit(main())
