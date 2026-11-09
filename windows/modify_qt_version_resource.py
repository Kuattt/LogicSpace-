"""CI-only: make a harmless version-resource edit in a copied Qt DLL.

The output is used only for a startup smoke test. It must never be packaged.
"""
from pathlib import Path
import sys


def modify(path: Path) -> None:
    path = Path(path)
    image = bytearray(path.read_bytes())
    needle = "Qt6Core.dll".encode("utf-16le")
    offset = image.find(needle)
    if offset < 0 or image.find(needle, offset + 1) >= 0:
        raise ValueError("Expected exactly one Qt6Core.dll version-resource string")
    image[offset + 16] = ord("D")  # OriginalFilename: Qt6Core.Dll
    path.write_bytes(image)


if __name__ == "__main__":
    modify(Path(sys.argv[1]))
