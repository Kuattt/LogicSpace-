"""Package verified upstream source archives for the 3.1.0 Windows release.

This script takes predownloaded official archives; it never fetches code or
executes a source archive. The caller must verify the output before upload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED


ARCHIVES = {
    "qtbase-everywhere-src-6.9.3.tar.xz": "c5a1a2f660356ec081febfa782998ae5ddbc5925117e64f50e4be9cd45b8dc6e",
    "qtimageformats-everywhere-src-6.9.3.tar.xz": "4fb26bdbfbd4b8e480087896514e11c33aba7b6b39246547355ea340c4572ffe",
    "qtsvg-everywhere-src-6.9.3.tar.xz": "db76aa3358cbbe6fce7da576ff4669cb9801920188c750d3b12783bbe97026e2",
    "pyside-setup-everywhere-src-6.9.3.tar.xz": "7cd2d5abb98f2e6f442b0e41f5fcf930e7312ae4b17f681316b1adc7b63bb172",
    "mesa-11.2.2.tar.xz": "40e148812388ec7c6d7b6657d5a16e2e8dabba8b97ddfceea5197947647bdfb4",
}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def package(source_dir: Path, output: Path) -> Path:
    source_dir = Path(source_dir)
    output = Path(output)
    for name, expected in ARCHIVES.items():
        path = source_dir / name
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Missing or incorrect upstream source archive: {name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"version": "6.9.3", "purpose": "Upstream library sources distributed with LogicSpace 3.1.0 Windows binaries",
                "qt_source": "https://download.qt.io/archive/qt/6.9/6.9.3/submodules/",
                "mesa_source": "https://archive.mesa3d.org/older-versions/11.x/11.2.2/",
                "sha256": ARCHIVES}
    with ZipFile(output, "w", ZIP_STORED) as archive:
        for name in sorted(ARCHIVES):
            archive.write(source_dir / name, name)
        archive.writestr("MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Source package failed ZIP integrity check")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("dist/windows/Qt-sources-6.9.3.zip"))
    args = parser.parse_args()
    result = package(args.source_dir, args.output)
    print(f"{result}: {result.stat().st_size} bytes, SHA-256 {digest(result)}")
