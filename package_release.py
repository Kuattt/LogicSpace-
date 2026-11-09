"""Build and verify an allowlisted, data-only source ZIP from audited Git files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import zipfile

from version import APP_VERSION

ROOT = Path(__file__).resolve().parent
PREFIX = f"LogicSpace-{APP_VERSION}/"
DIRECTORIES = {".github", "docs", "examples", "licenses", "resources", "tests"}
WINDOWS_FILES = {"windows/LogicSpace.nsi.in", "windows/LogicSpace.spec",
                 "windows/README-BUILD.txt", "windows/build.py",
                 "windows/requirements-build.txt"}
ROOT_NAMES = {".gitignore", ".gitattributes", "README.md", "CHANGELOG.md", "RELEASE_NOTES.md",
              "CONTRIBUTING.md", "SECURITY.md", "LICENSE.md",
              "COMMERCIAL-LICENSE.md", "THIRD_PARTY_NOTICES.md",
              "requirements.txt", "install.sh", "launch.sh"}
SUFFIXES = {".py", ".sh", ".md", ".txt", ".json", ".sv", ".v", ".asm",
            ".bin", ".hex", ".png", ".svg", ".yml", ".yaml"}
REQUIRED = {"README.md", "RELEASE_NOTES.md", "requirements.txt", "install.sh",
            "launch.sh", "main.py", "engine.py", "version.py",
            "LICENSE.md", "COMMERCIAL-LICENSE.md", "THIRD_PARTY_NOTICES.md",
            "licenses/LGPL-3.0.txt", "licenses/GPL-3.0.txt",
            "licenses/Apache-2.0.txt", "licenses/Python-3.12.txt"} | WINDOWS_FILES


def release_files(root=ROOT):
    raw = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=root)
    files = []
    for entry in raw.split(b"\0"):
        if not entry: continue
        name = entry.decode("utf-8")
        path = Path(name)
        # The website is built and published separately from the desktop source ZIP.
        if path.parts[0] == "website":
            continue
        if (path.is_absolute() or ".." in path.parts or
                not (len(path.parts) == 1 and (path.name in ROOT_NAMES or path.suffix == ".py") or
                     path.parts[0] in DIRECTORIES and path.suffix in SUFFIXES or
                     name in WINDOWS_FILES)):
            raise ValueError(f"Refusing unreviewed release path: {name}")
        full = root / path
        if not full.is_file() or full.is_symlink() or full.stat().st_size > 8 * 1024 * 1024:
            raise ValueError(f"Release source is missing, a link or too large: {name}")
        files.append(name)
    if not REQUIRED.issubset(files):
        raise ValueError("Release is missing required files: " + ", ".join(sorted(REQUIRED - set(files))))
    if sum((root / name).stat().st_size for name in files) > 60 * 1024 * 1024:
        raise ValueError("Release source exceeds 60 MiB")
    return sorted(files)


def build_package(output, root=ROOT):
    files = release_files(root)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"format": "logicspace-source-release", "version": APP_VERSION,
                "files": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                          for name in files}}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for name in files:
            info = zipfile.ZipInfo(PREFIX + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if name in ("install.sh", "launch.sh") else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, (root / name).read_bytes())
        info = zipfile.ZipInfo(PREFIX + "release-manifest.json", date_time=(2026, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(info, json.dumps(manifest, indent=2).encode("utf-8"))
    verify_package(output)
    return output


def verify_package(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 500 or any(
                not name.startswith(PREFIX) or ".." in Path(name).parts for name in names):
            raise ValueError("Source ZIP has invalid paths or duplicate entries")
        manifest_name = PREFIX + "release-manifest.json"
        if manifest_name not in names or archive.getinfo(manifest_name).file_size > 1024 * 1024:
            raise ValueError("Source ZIP has no bounded manifest")
        manifest = json.loads(archive.read(manifest_name))
        if manifest.get("format") != "logicspace-source-release" or manifest.get("version") != APP_VERSION:
            raise ValueError("Source ZIP has invalid release metadata")
        if not REQUIRED.issubset(manifest.get("files", {})):
            raise ValueError("Source ZIP is missing required release or license documents")
        expected = {PREFIX + name for name in manifest["files"]} | {manifest_name}
        if set(names) != expected:
            raise ValueError("Source ZIP members differ from its manifest")
        for name, digest in manifest["files"].items():
            info = archive.getinfo(PREFIX + name)
            if info.file_size > 8 * 1024 * 1024 or hashlib.sha256(archive.read(info)).hexdigest() != digest:
                raise ValueError(f"Source ZIP has modified content: {name}")
        return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=f"dist/LogicSpace-{APP_VERSION}-source.zip")
    args = parser.parse_args()
    path = build_package(args.output)
    print(f"Verified {path} ({path.stat().st_size} bytes)")
