"""Source ZIP allowlist, checksums and required launch files."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from package_release import build_package, release_files, verify_package, PREFIX, REQUIRED
from version import APP_VERSION


@unittest.skipUnless(shutil.which("git"), "Git CLI required to construct source-release fixtures")
class ReleasePackageTests(unittest.TestCase):
    def make_repo(self, root):
        subprocess.run(["git", "init", "-q", root], check=True)
        for name in REQUIRED:
            path = Path(root) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)

    def test_build_and_verify_source_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"; root.mkdir()
            self.make_repo(root)
            output = Path(folder) / "release.zip"
            build_package(output, root)
            manifest = verify_package(output)
            self.assertEqual(manifest["version"], APP_VERSION)
            with zipfile.ZipFile(output) as archive:
                self.assertIn(PREFIX + "launch.sh", archive.namelist())
                self.assertIn(PREFIX + "windows/build.py", archive.namelist())
                for name in ("LICENSE.md", "COMMERCIAL-LICENSE.md", "THIRD_PARTY_NOTICES.md",
                             "licenses/LGPL-3.0.txt", "licenses/GPL-3.0.txt",
                             "licenses/Apache-2.0.txt", "licenses/Python-3.12.txt"):
                    self.assertEqual(archive.read(PREFIX + name), name.encode("utf-8"))
                self.assertEqual(archive.read(PREFIX + "engine.py"), b"engine.py")
                self.assertEqual((archive.getinfo(PREFIX + "launch.sh").external_attr >> 16) & 0o777,
                                 0o755)

    def test_unreviewed_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"; root.mkdir()
            self.make_repo(root)
            (root / "secrets.env").write_text("private", encoding="utf-8")
            subprocess.run(["git", "add", "secrets.env"], cwd=root, check=True)
            self.assertRaisesRegex(ValueError, "Refusing", release_files, root)

    def test_corrupted_member_fails_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"; root.mkdir()
            self.make_repo(root)
            output = Path(folder) / "release.zip"
            build_package(output, root)
            with zipfile.ZipFile(output) as archive:
                content = {name: archive.read(name) for name in archive.namelist()}
            content[PREFIX + "engine.py"] = b"altered"
            with zipfile.ZipFile(output, "w") as archive:
                for name, body in content.items(): archive.writestr(name, body)
            self.assertRaisesRegex(ValueError, "modified", verify_package, output)

    def test_missing_license_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"; root.mkdir()
            self.make_repo(root)
            (root / "LICENSE.md").unlink()
            self.assertRaisesRegex(ValueError, "missing", release_files, root)


if __name__ == "__main__": unittest.main()
