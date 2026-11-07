"""Updater checks metadata only; source installations never replace executable files."""
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PySide6.QtWidgets import QApplication, QLabel

from update_model import (AUTO_INSTALL_SUPPORTED, Release, UpdateSettings, Version,
                          fetch_release, find_update, parse_release, update_destination)
from update_view import UpdateDialog, UpdateSettingsDialog


def release(tag="v3.1.0", *, prerelease=False):
    return {"tag_name": tag, "html_url": f"https://github.com/Kuattt/LogicSpace-/releases/tag/{tag}",
            "body": "Changes", "draft": False, "prerelease": prerelease}


class Response:
    def __init__(self, data): self.data = io.BytesIO(json.dumps(data).encode())
    def read(self, size=-1): return self.data.read(size)
    def __enter__(self): return self
    def __exit__(self, *_): return False


class VersionTests(unittest.TestCase):
    def test_semver_precedence(self):
        ordered = ("1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta",
                   "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11",
                   "1.0.0-rc.1", "1.0.0")
        self.assertEqual(sorted(map(Version.parse, reversed(ordered))), list(map(Version.parse, ordered)))
        self.assertEqual(Version.parse("v3.0.0+build.4"), Version.parse("3.0.0"))
        for invalid in ("3.0", "03.0.0", "3.0.0-beta.01", "3.0.0-", "3.0.0-rc_1"):
            self.assertRaises(ValueError, Version.parse, invalid)

    def test_release_validation_and_official_url(self):
        self.assertEqual(parse_release(release()).tag, "v3.1.0")
        bad = release(); bad["html_url"] = "https://github.com.evil.example/Kuattt/LogicSpace-/releases/tag/v3.1.0"
        self.assertRaises(ValueError, parse_release, bad)
        bad = release(); bad["draft"] = True
        self.assertRaises(ValueError, parse_release, bad)
        bad = release("v3.1.0-beta.1", prerelease=False)
        self.assertRaises(ValueError, parse_release, bad)

    def test_api_latest_beta_filter_and_no_internet(self):
        seen = []
        def opener(request, timeout):
            seen.append((request.full_url, timeout))
            return Response(release())
        self.assertEqual(fetch_release(opener=opener).tag, "v3.1.0")
        self.assertEqual(seen, [("https://api.github.com/repos/Kuattt/LogicSpace-/releases/latest", 3)])
        releases = [release("v3.2.0-beta.1", prerelease=True), release("v3.1.0")]
        self.assertEqual(fetch_release(include_prerelease=True,
                                       opener=lambda *_args, **_kwargs: Response(releases)).tag,
                         "v3.2.0-beta.1")
        self.assertRaisesRegex(ValueError, "Cannot check", fetch_release,
                               opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")))
        self.assertRaisesRegex(ValueError, "too large", fetch_release,
                               opener=lambda *_args, **_kwargs: Response({"body": "x" * 300000}))

    def test_find_update_and_no_auto_install(self):
        new = parse_release(release())
        self.assertEqual(find_update(fetch=lambda **_: new).tag, "v3.1.0")
        self.assertIsNone(find_update(current="3.1.0", fetch=lambda **_: new))
        beta = parse_release(release("v3.2.0-beta.1", prerelease=True))
        self.assertIsNone(find_update(fetch=lambda **_: beta))
        self.assertFalse(AUTO_INSTALL_SUPPORTED)
        self.assertEqual(update_destination(new), new.url)
        forged = Release(new.version, new.tag, "https://example.com/download", new.notes, False)
        self.assertRaises(ValueError, update_destination, forged)


class SettingsTests(unittest.TestCase):
    def test_daily_limit_opt_out_and_prerelease_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            store = UpdateSettings(Path(folder) / "updater.json")
            now = datetime(2026, 11, 7, tzinfo=timezone.utc)
            self.assertTrue(store.due(now))
            store.checked(now)
            self.assertFalse(store.due(now + timedelta(hours=23)))
            self.assertTrue(store.due(now + timedelta(days=1)))
            data = store.load(); data.update(auto_check=False, include_prerelease=True)
            store.save(data)
            self.assertFalse(store.due(now + timedelta(days=2)))
            self.assertTrue(store.load()["include_prerelease"])
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)

    def test_corrupt_settings_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "updater.json"
            path.write_text("{broken", encoding="utf-8")
            self.assertRaises(ValueError, UpdateSettings(path).load)
            self.assertEqual(path.read_text(), "{broken")

    def test_user_data_remains_untouched_by_release_check(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "projects" / "my_cpu.json"
            library = root / "component_library" / "my_block.json"
            for path in (project, library):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"personal data")
            before = {path: path.read_bytes() for path in (project, library)}
            store = UpdateSettings(root / "updater.json")
            store.checked()
            find_update(fetch=lambda **_: parse_release(release()))
            self.assertEqual({path: path.read_bytes() for path in before}, before)


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_update_dialog_is_read_only_and_settings_are_editable(self):
        found = parse_release(release())
        dialog = UpdateDialog(found)
        self.assertTrue(any("Current: 3.0.0" in label.text()
                            for label in dialog.findChildren(QLabel)))
        with tempfile.TemporaryDirectory() as folder:
            class Controller: pass
            controller = Controller(); controller.settings = UpdateSettings(Path(folder) / "settings.json")
            settings = UpdateSettingsDialog(controller)
            settings.automatic.setChecked(False)
            settings.beta.setChecked(True)
            settings.save()
            self.assertFalse(controller.settings.load()["auto_check"])
            self.assertTrue(controller.settings.load()["include_prerelease"])


if __name__ == "__main__": unittest.main()
