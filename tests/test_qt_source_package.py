"""The third-party source asset rejects missing or altered upstream archives."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from windows import package_qt_sources


class QtSourcePackageTests(unittest.TestCase):
    def test_verified_source_bundle_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "qtbase.tar.xz"
            source.write_bytes(b"known archive")
            import hashlib
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            with patch.object(package_qt_sources, "ARCHIVES", {source.name: expected}):
                output = root / "sources.zip"
                package_qt_sources.package(root, output)
                with ZipFile(output) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(archive.read(source.name), b"known archive")
                    self.assertIn(expected.encode(), archive.read("MANIFEST.json"))
                source.write_bytes(b"altered archive")
                with self.assertRaisesRegex(ValueError, "incorrect upstream source"):
                    package_qt_sources.package(root, output)


if __name__ == "__main__":
    unittest.main()
