"""The desktop source archive must exclude the independently built website."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from package_release import REQUIRED, release_files


class WebsiteReleaseSeparationTests(unittest.TestCase):
    def test_website_files_are_not_desktop_archive_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for name in REQUIRED:
                (root / name).write_text(name, encoding="utf-8")
            site = root / "website"
            site.mkdir()
            (site / "index.html").write_text("<h1>LogicSpace</h1>", encoding="utf-8")
            (site / ".gitignore").write_text("dist/\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            files = release_files(root)
            self.assertFalse(any(name.startswith("website/") for name in files))
            self.assertIn("main.py", files)


if __name__ == "__main__":
    unittest.main()
