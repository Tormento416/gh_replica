import tempfile
import unittest
from pathlib import Path

from hyrlink_platform.ade_migrations import discover
from hyrlink_platform.contracts import PlatformError


class MigrationDiscoveryTests(unittest.TestCase):
    def test_nested_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "ade_001_test.sql").write_text("BEGIN;\nCOMMIT;\nSELECT 1;\nCOMMIT;\n")
            with self.assertRaisesRegex(PlatformError, "invalid_migration_transaction"):
                discover(directory)

    def test_missing_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "ade_002_test.sql").write_text("BEGIN;\nSELECT 1;\nCOMMIT;\n")
            with self.assertRaisesRegex(PlatformError, "migration_sequence_invalid"):
                discover(directory)

    def test_unwrapped_migration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "ade_001_test.sql").write_text("SELECT 1;")
            with self.assertRaisesRegex(PlatformError, "invalid_migration_transaction"):
                discover(directory)
