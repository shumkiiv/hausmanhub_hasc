#!/usr/bin/env python3
"""Keep the HausmanHub product name distinct from the HACS installer."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Iterable

from check_repository_boundary import RepositoryCheckError, RepositoryFile, tracked_files


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEGACY_PRODUCT_TOKEN = re.compile(
    rb"(?<![A-Za-z0-9_])HA" + rb"SC(?![A-Za-z0-9_])"
)
FORBIDDEN_TEXT = (
    (LEGACY_PRODUCT_TOKEN, "old temporary product name"),
    (re.compile(rb"hausman-" + rb"hasc"), "old public contract name"),
    (
        re.compile(rb"github\.com/shumkiiv/hausmanhub_" + rb"hasc"),
        "old GitHub repository address",
    ),
)


def main() -> int:
    """Check the current indexed project text without network access."""

    try:
        files = tracked_files(REPOSITORY_ROOT)
    except RepositoryCheckError as exc:
        print(f"Product naming check could not run: {exc}", file=sys.stderr)
        return 2

    findings = find_product_naming_violations(files)
    if findings:
        print("Product naming check failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    print("Product naming check passed: HausmanHub and HACS are distinct.")
    return 0


def find_product_naming_violations(
    files: Iterable[RepositoryFile],
) -> tuple[str, ...]:
    """Return old public names found in text files in deterministic order."""

    findings: list[str] = []
    for file in files:
        if b"\0" in file.content:
            continue
        for pattern, label in FORBIDDEN_TEXT:
            for matched in pattern.finditer(file.content):
                line_number = file.content.count(b"\n", 0, matched.start()) + 1
                findings.append(f"{file.path}:{line_number}: {label}")
    return tuple(sorted(findings))


if __name__ == "__main__":
    raise SystemExit(main())
