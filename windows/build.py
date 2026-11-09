"""Build both Windows distributions from the same PyInstaller onedir output.

Run on 64-bit Windows with Python 3.12, windows/requirements-build.txt and
NSIS 3 (makensis) installed. No source checkout is modified by install.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "windows"
STAGE = BUILD / "dist" / "LogicSpace"
OUTPUT = ROOT / "dist" / "windows"
VERSION = "3.1.0"
RELEASE_DOCUMENTS = (
    "LICENSE.md", "COMMERCIAL-LICENSE.md", "THIRD_PARTY_NOTICES.md",
    "licenses/LGPL-3.0.txt", "licenses/GPL-3.0.txt",
    "licenses/Apache-2.0.txt", "licenses/Python-3.12.txt",
    "licenses/Qt-6.9.3-attributions.txt",
    "licenses/Mesa-llvmpipe-attribution.txt",
    "licenses/NSIS-zlib-license.txt",
    "docs/qt-source-and-replacement-3.1.0.md",
)
MICROSOFT_RUNTIME_NAMES = {"ucrtbase.dll", "concrt140.dll", "vccorlib140.dll"}
MICROSOFT_RUNTIME_PREFIXES = ("api-ms-win-", "msvcp140", "vcruntime140", "vcamp140", "vcomp140")


def is_microsoft_runtime(path):
    name = Path(path).name.lower()
    return name in MICROSOFT_RUNTIME_NAMES or any(name.startswith(prefix) and name.endswith(".dll")
                                                   for prefix in MICROSOFT_RUNTIME_PREFIXES)


def remove_microsoft_runtimes(stage):
    """Require the official system VC++ runtime instead of repackaging DLL copies."""
    removed = []
    for path in Path(stage).rglob("*"):
        if path.is_file() and is_microsoft_runtime(path):
            path.unlink()
            removed.append(path.relative_to(stage).as_posix())
    return removed


def require_windows_x64():
    if sys.platform != "win32" or struct.calcsize("P") != 8 or platform.machine().upper() not in ("AMD64", "X86_64"):
        raise RuntimeError("Build on Windows 10/11 x64 with 64-bit Python 3.12")
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("This build is pinned to Python 3.12")


def find_makensis():
    candidates = [os.environ.get("NSIS_COMPILER"), shutil.which("makensis"), shutil.which("makensis.exe")]
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        root = os.environ.get(variable)
        if root:
            candidates.append(str(Path(root) / "NSIS" / "makensis.exe"))
    for path in candidates:
        if path and Path(path).is_file():
            return Path(path)
    raise RuntimeError("NSIS command-line compiler makensis is required")


def make_icon(png_path, ico_path):
    """ICO container with the project's existing 256x256 PNG; no image library."""
    png = Path(png_path).read_bytes()
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or struct.unpack_from(">II", png, 16) != (256, 256):
        raise ValueError("LogicSpace icon must be a 256x256 PNG")
    ico_path = Path(ico_path)
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    header = struct.pack("<HHH", 0, 1, 1)
    directory = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    ico_path.write_bytes(header + directory + png)


def machine_type(exe):
    with Path(exe).open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError(f"Not a Windows executable: {exe}")
        stream.seek(0x3C)
        pe_offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(pe_offset)
        if stream.read(4) != b"PE\0\0":
            raise ValueError(f"Invalid PE signature: {exe}")
        return struct.unpack("<H", stream.read(2))[0]


def verify_stage(stage):
    exe = stage / "LogicSpace.exe"
    if not exe.is_file() or machine_type(exe) != 0x8664:
        raise ValueError("Portable LogicSpace.exe is missing or is not x64")
    internal = stage / "_internal"
    for name in ("resources/logicspace.png", "examples/half_adder.json", "README.md"):
        if not (internal / name).is_file():
            raise ValueError(f"Missing bundled resource: {name}")
    if not list(internal.rglob("qwindows.dll")):
        raise ValueError("Qt Windows platform plugin qwindows.dll is missing")
    if any(path.suffix == ".py" for path in stage.rglob("*")):
        raise ValueError("Raw Python source was unexpectedly included")
    bundled_runtime = [path for path in stage.rglob("*") if path.is_file() and is_microsoft_runtime(path)]
    if bundled_runtime:
        raise ValueError(f"Microsoft runtime DLLs must not be bundled: {bundled_runtime[0]}")
    for name in RELEASE_DOCUMENTS:
        bundled = stage / name
        source = ROOT / name
        if not source.is_file() or not bundled.is_file() or digest(source) != digest(bundled):
            raise ValueError(f"Missing or modified release document: {name}")


def stage_release_documents(stage=STAGE):
    """Place reviewable notices beside the executable in both Windows packages."""
    for name in RELEASE_DOCUMENTS:
        source = ROOT / name
        if not source.is_file():
            raise ValueError(f"Missing release document: {name}")
        destination = Path(stage) / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def write_readme(path):
    path.write_text(
        f"LogicSpace {VERSION} for Windows 10 (1809+) / Windows 11 x64\n"
        "\nPortable: extract the full ZIP to a writable directory and run LogicSpace\\LogicSpace.exe.\n"
        "Installer: run LogicSpace-Setup.exe and follow the wizard. It installs for the current user.\n"
        "No separate Python or PySide6 installation is required.\n"
        "Microsoft Visual C++ Redistributable x64 (2015-2022 or compatible newer)\n"
        "must be installed separately from Microsoft before launch.\n"
        "https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist\n"
        "\nQt/PySide6 source archives are supplied as Qt-sources-6.9.3.zip on the\n"
        "same LogicSpace 3.1.0 GitHub Release. See the bundled\n"
        "docs\\qt-source-and-replacement-3.1.0.md for library replacement steps.\n"
        "\nProjects: choose a location in Documents or another folder you control.\n"
        "Settings, templates, library and benchmark history: %LOCALAPPDATA%\\LogicSpace\\\n"
        "Uninstalling the application does not remove these user files.\n"
        "\nExternal HDL compilation, synthesis and linting require the Linux Bubblewrap sandbox\n"
        "and are unavailable in this Windows build. Internal HDL editing, import/export,\n"
        "test vectors and the LogicSpace simulator remain available. GTKWave can be opened\n"
        "if separately installed and found on PATH. Automatic update installation is not supported;\n"
        "the app can open the official GitHub release page for manual updates.\n"
        "\nThis package is unsigned. Windows SmartScreen may warn until a trusted code-signing\n"
        "certificate is provided. Do not disable Windows security features.\n",
        encoding="utf-8",
    )


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def package():
    """Package a verified Windows stage; may run on Linux with native makensis."""
    compiler = find_makensis()
    from version import APP_VERSION
    if APP_VERSION != VERSION:
        raise RuntimeError("Installer version and application version disagree")
    icon = BUILD / "logicspace.ico"
    make_icon(ROOT / "resources" / "logicspace.png", icon)
    verify_stage(STAGE)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    portable = OUTPUT / "LogicSpace-Windows-x64.zip"
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(STAGE.rglob("*")):
            if path.is_file():
                archive.write(path, "LogicSpace/" + path.relative_to(STAGE).as_posix())
    with zipfile.ZipFile(portable) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Portable archive has a damaged member: {bad}")
        if "LogicSpace/LogicSpace.exe" not in archive.namelist():
            raise ValueError("Portable archive does not contain LogicSpace.exe")

    installer = OUTPUT / "LogicSpace-Setup.exe"
    template = (ROOT / "windows" / "LogicSpace.nsi.in").read_text(encoding="utf-8")
    def literal(path):
        value = str(path)
        if '"' in value or '$' in value:
            raise ValueError("NSIS source paths cannot contain quotes or dollar signs")
        return value
    files = [path for path in sorted(STAGE.rglob("*")) if path.is_file()]
    install_commands = []
    for path in files:
        relative = path.relative_to(STAGE)
        destination = "\\".join(relative.parent.parts)
        install_commands.append(f'  SetOutPath "$INSTDIR{chr(92) + destination if destination else ""}"')
        install_commands.append(f'  File "{literal(path)}"')
    uninstall_commands = [f'  Delete "$INSTDIR\\{literal(path.relative_to(STAGE)).replace(os.sep, chr(92))}"'
                          for path in files]
    directories = sorted((path.relative_to(STAGE) for path in STAGE.rglob("*") if path.is_dir()),
                         key=lambda path: (len(path.parts), str(path)), reverse=True)
    remove_dirs = [f'  RMDir "$INSTDIR\\{literal(path).replace(os.sep, chr(92))}"' for path in directories]
    script = (template.replace("@VERSION4@", VERSION + ".0")
             .replace("@VERSION@", VERSION)
             .replace("@OUTPUT@", literal(installer))
             .replace("@ICON@", literal(icon))
             .replace("@INSTALL_FILES@", "\n".join(install_commands))
             .replace("@UNINSTALL_FILES@", "\n".join(uninstall_commands))
             .replace("@REMOVE_DIRS@", "\n".join(remove_dirs)))
    script_path = BUILD / "LogicSpace.generated.nsi"
    script_path.write_text(script, encoding="utf-8")
    subprocess.run([str(compiler), str(script_path)], cwd=ROOT, check=True)
    if not installer.is_file() or installer.stat().st_size < 1024:
        raise ValueError("NSIS did not produce a valid installer executable")
    with installer.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("NSIS did not produce a valid installer executable")
    write_readme(OUTPUT / "README-Windows.txt")
    (OUTPUT / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in (installer, portable)),
        encoding="ascii",
    )
    for path in (installer, portable):
        print(f"{path}: {path.stat().st_size} bytes, SHA-256 {digest(path)}")


def build():
    require_windows_x64()
    sys.path.insert(0, str(ROOT))
    import PySide6
    import PyInstaller
    if PySide6.__version__ != "6.9.3" or PyInstaller.__version__ != "6.22.3":
        raise RuntimeError("Install exact versions from windows/requirements-build.txt")
    make_icon(ROOT / "resources" / "logicspace.png", BUILD / "logicspace.ico")
    if STAGE.exists():
        shutil.rmtree(STAGE)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--workpath", str(BUILD / "work"), "--distpath", str(BUILD / "dist"),
                    str(ROOT / "windows" / "LogicSpace.spec")], cwd=ROOT, check=True)
    removed = remove_microsoft_runtimes(STAGE)
    print(f"Removed {len(removed)} bundled Microsoft runtime DLLs; system VC++ runtime required")
    stage_release_documents(STAGE)
    package()


if __name__ == "__main__":
    try:
        build()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Windows build failed: {error}", file=sys.stderr)
        raise SystemExit(1)
