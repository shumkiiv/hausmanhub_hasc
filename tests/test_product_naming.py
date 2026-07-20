"""Tests for the distinction between HausmanHub and the HACS installer."""

from __future__ import annotations

from pathlib import PurePosixPath
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_product_naming as naming  # noqa: E402
from check_repository_boundary import RepositoryFile, tracked_files  # noqa: E402


class ProductNamingTest(unittest.TestCase):
    """Prevent the old temporary name from returning to public text."""

    def test_current_prepared_project_uses_hausmanhub_and_hacs(self) -> None:
        self.assertEqual((), naming.find_product_naming_violations(tracked_files(ROOT)))

    def test_old_product_contract_and_repository_names_are_rejected(self) -> None:
        files = (
            RepositoryFile(PurePosixPath("a.md"), b"old HA" + b"SC product"),
            RepositoryFile(PurePosixPath("b.json"), b"hausman-" + b"hasc-home"),
            RepositoryFile(
                PurePosixPath("c.md"),
                b"https://github.com/shumkiiv/hausmanhub_" + b"hasc",
            ),
        )

        findings = naming.find_product_naming_violations(files)

        self.assertEqual(3, len(findings))
        self.assertTrue(any("old temporary product name" in item for item in findings))
        self.assertTrue(any("old public contract name" in item for item in findings))
        self.assertTrue(any("old GitHub repository address" in item for item in findings))

    def test_hacs_installer_name_is_allowed(self) -> None:
        files = (
            RepositoryFile(
                PurePosixPath("install.md"),
                "Установите HausmanHub через HACS".encode(),
            ),
        )

        self.assertEqual((), naming.find_product_naming_violations(files))


if __name__ == "__main__":
    unittest.main()
