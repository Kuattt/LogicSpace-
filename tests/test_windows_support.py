"""Portable-build and Windows path regressions that run without Windows."""
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from app_paths import user_data_dir
import hdl_tools
import toolchain_model
from windows.build import make_icon, machine_type, verify_stage


class WindowsCompatibilityTests(unittest.TestCase):
    def test_installer_preserves_user_files_and_uses_per_user_registry(self):
        template = (Path(__file__).resolve().parents[1] / "windows" / "LogicSpace.nsi.in").read_text(encoding="utf-8")
        self.assertIn("RequestExecutionLevel user", template)
        self.assertIn("$LOCALAPPDATA\\Programs\\LogicSpace", template)
        self.assertIn("WriteRegStr HKCU", template)
        self.assertNotIn("RMDir /r", template)
        self.assertNotIn("DeleteRegKey HKCU \"Software\\LogicSpace\"", template)

    def test_windows_data_is_not_in_app_folder(self):
        with patch("app_paths.sys.platform", "win32"), \
             patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Ada\AppData\Local"}):
            path = user_data_dir()
        self.assertEqual(path, Path(r"C:\Users\Ada\AppData\Local") / "LogicSpace")
        self.assertNotIn(".local/share", str(path))

    def test_linux_location_remains_compatible(self):
        with patch("app_paths.sys.platform", "linux"), \
             patch.dict(os.environ, {"XDG_DATA_HOME": "/tmp/logicspace-xdg"}):
            self.assertEqual(user_data_dir(), Path("/tmp/logicspace-xdg/logicspace"))
        with patch("app_paths.sys.platform", "linux"), \
             patch.dict(os.environ, {"XDG_DATA_HOME": ""}):
            self.assertEqual(user_data_dir(), Path.home() / ".local/share/logicspace")

    def test_external_hdl_reports_unsupported_windows_sandbox(self):
        with patch.object(toolchain_model, "resource", None):
            with self.assertRaisesRegex(ValueError, "unavailable on Windows"):
                toolchain_model.run_restricted(["iverilog"], ".")
            with patch.object(toolchain_model.shutil, "which", return_value=r"C:\Tools\yosys.exe"):
                status = toolchain_model.detect_tool("yosys")
            self.assertTrue(status["installed"])
            self.assertFalse(status["available"])
        with patch.object(hdl_tools.os, "name", "nt"):
            available, reason = hdl_tools.external_availability()
        self.assertFalse(available)
        self.assertIn("Windows", reason)

    def test_ico_wraps_real_png_and_stage_checks_x64_and_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            png = root / "icon.png"
            png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + struct.pack(">II", 256, 256))
            make_icon(png, root / "icon.ico")
            icon = (root / "icon.ico").read_bytes()
            self.assertEqual(icon[:6], b"\0\0\x01\0\x01\0")
            self.assertEqual(icon[22:], png.read_bytes())

            stage = root / "LogicSpace"
            internal = stage / "_internal"
            (internal / "resources").mkdir(parents=True)
            (internal / "examples").mkdir()
            (internal / "PySide6" / "Qt" / "plugins" / "platforms").mkdir(parents=True)
            (internal / "resources" / "logicspace.png").write_bytes(b"icon")
            (internal / "examples" / "half_adder.json").write_bytes(b"{}")
            (internal / "README.md").write_bytes(b"guide")
            (internal / "PySide6" / "Qt" / "plugins" / "platforms" / "qwindows.dll").write_bytes(b"plugin")
            exe = stage / "LogicSpace.exe"
            image = bytearray(256)
            image[:2] = b"MZ"
            struct.pack_into("<I", image, 0x3C, 128)
            image[128:132] = b"PE\0\0"
            struct.pack_into("<H", image, 132, 0x8664)
            exe.write_bytes(image)
            self.assertEqual(machine_type(exe), 0x8664)
            verify_stage(stage)
            (internal / "examples" / "half_adder.json").unlink()
            with self.assertRaisesRegex(ValueError, "Missing bundled resource"):
                verify_stage(stage)


if __name__ == "__main__":
    unittest.main()
