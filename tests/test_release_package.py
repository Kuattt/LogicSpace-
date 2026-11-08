"""Source ZIP allowlist, checksums and required launch files."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from package_release import build_package, release_files, verify_package, PREFIX


@unittest.skipUnless(shutil.which("git"), "Git CLI required to construct source-release fixtures")
class ReleasePackageTests(unittest.TestCase):
    def make_repo(self, root):
        subprocess.run(["git", "init", "-q", root], check=True)
        for name in ("README.md", "RELEASE_NOTES.md", "requirements.txt", "install.sh",
                     "launch.sh", "main.py", "engine.py", "version.py"):
            path = Path(root) / name
            path.write_text(name, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)

    def test_build_and_verify_source_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"; root.mkdir()
            self.make_repo(root)
            output = Path(folder) / "release.zip"
            build_package(output, root)
            manifest = verify_package(output)
            self.assertEqual(manifest["version"], "3.0.0")
            with zipfile.ZipFile(output) as archive:
                self.assertIn(PREFIX + "launch.sh", archive.namelist())
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


if __name__ == "__main__": unittest.main()
