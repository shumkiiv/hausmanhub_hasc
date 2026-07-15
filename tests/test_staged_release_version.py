"""Tests for the local HACS-visible version boundary."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path, PurePosixPath
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_staged_release_version as release_version  # noqa: E402


class StagedReleaseVersionTest(unittest.TestCase):
    """Keep HACS-visible changes tied to a higher integration version."""

    def test_only_integration_or_hacs_metadata_requires_a_version_increase(self) -> None:
        self.assertFalse(
            release_version.has_release_relevant_change(
                (PurePosixPath("docs/read-only-skeleton.md"),)
            )
        )
        self.assertTrue(
            release_version.has_release_relevant_change(
                (PurePosixPath("custom_components/hausman_hub/config_flow.py"),)
            )
        )
        self.assertTrue(
            release_version.has_release_relevant_change((PurePosixPath("hacs.json"),))
        )

    def test_same_or_lower_version_is_rejected_after_a_release_relevant_change(self) -> None:
        self.assertIn(
            "must increase from 0.2.0",
            release_version.version_change_finding("0.2.0", "0.2.0") or "",
        )
        self.assertIn(
            "staged version is 0.1.9",
            release_version.version_change_finding("0.2.0", "0.1.9") or "",
        )

    def test_higher_version_is_accepted(self) -> None:
        self.assertIsNone(release_version.version_change_finding("0.2.0", "0.2.1"))
        self.assertIsNone(release_version.version_change_finding("0.2.9", "0.3.0"))
        self.assertIsNone(release_version.version_change_finding("0.9.9", "1.0.0"))

    def test_malformed_versions_are_rejected(self) -> None:
        for version in ("0.2", "0.02.0", "v0.2.0", "0.2.0-beta"):
            with self.subTest(version=version):
                with self.assertRaisesRegex(RuntimeError, "three non-negative numbers"):
                    release_version.parse_release_version(version)

    def test_main_rejects_an_unchanged_version_for_a_staged_integration_change(self) -> None:
        output = io.StringIO()
        with (
            patch.object(
                release_version,
                "staged_file_paths",
                return_value=(PurePosixPath("custom_components/hausman_hub/__init__.py"),),
            ),
            patch.object(
                release_version,
                "manifest_version",
                side_effect=("0.2.0", "0.2.0"),
            ),
            redirect_stdout(io.StringIO()),
            redirect_stderr(output),
        ):
            result = release_version.main()

        self.assertEqual(1, result)
        self.assertIn("must increase from 0.2.0", output.getvalue())

    def test_staged_paths_include_removed_and_type_changed_integration_files(self) -> None:
        completed = subprocess.CompletedProcess(
            ("git", "diff"),
            0,
            stdout=(
                b"custom_components/hausman_hub/removed_module.py\0"
                b"custom_components/hausman_hub/type_changed_module.py\0"
                b"docs/read-only-skeleton.md\0"
            ),
            stderr=b"",
        )
        with patch.object(release_version, "run_git", return_value=completed) as run_git:
            paths = release_version.staged_file_paths(ROOT)

        self.assertEqual(
            (
                PurePosixPath("custom_components/hausman_hub/removed_module.py"),
                PurePosixPath("custom_components/hausman_hub/type_changed_module.py"),
                PurePosixPath("docs/read-only-skeleton.md"),
            ),
            paths,
        )
        self.assertTrue(release_version.has_release_relevant_change(paths))
        run_git.assert_called_once_with(
            ROOT,
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMRDT",
            "-z",
        )


if __name__ == "__main__":
    unittest.main()
