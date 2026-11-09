# Qt/PySide6 source and replacement information for LogicSpace 3.1.0

The Windows package uses separate Qt 6.9.3 and PySide6 6.9.3 DLL/PYD files.
These libraries remain under their own licenses; the proposed LogicSpace
license does not restrict your rights in them. See `licenses/LGPL-3.0.txt`,
`THIRD_PARTY_NOTICES.md`, and the official [Qt LGPL guidance](https://www.qt.io/development/open-source-lgpl-obligations).

The `Qt-sources-6.9.3.zip` asset on the **same LogicSpace 3.1.0 GitHub Release**
contains the upstream Qt 6.9.3 Core/GUI/Widgets/Network, Image Formats and
SVG source archives, the Qt for Python 6.9.3 source archive, and a Mesa 11.2.2
source archive. It is provided alongside the Windows binaries, without a
request, purchase or account. Each archive and its SHA-256 are recorded in
`MANIFEST.json` inside that asset. The original source archives are also
available from [Qt](https://download.qt.io/archive/qt/6.9/6.9.3/submodules/)
and [Mesa](https://archive.mesa3d.org/older-versions/11.x/11.2.2/).

The Qt/PySide6 binaries are dynamically loaded from the unpacked application.
To use a compatible modified build, close LogicSpace and replace the desired
DLL/PYD in `LogicSpace/_internal/PySide6/` (or the same path in the installed
folder) with a binary built for Windows x64, CPython 3.12 where applicable,
and a compatible Qt/PySide6 ABI. Keep the original file as a backup. The
per-user installer places these files under a user-writable directory and
does not enforce a code-signature or hash check on replacement libraries.
Restart LogicSpace afterwards. If the application fails to load, restore the
original file. Qt's [Windows build instructions](https://doc.qt.io/qt-6/windows-building.html)
and PySide6's [build instructions](https://doc.qt.io/qtforpython-6/building_from_source/windows.html)
describe the toolchain needed to build compatible libraries. Qt libraries
must be replaced consistently when ABI dependencies require it.

This document describes a method to replace compatible libraries; it does
not promise that every arbitrary modification will work. The source bundle
and binary provenance are documented in
`docs/windows-binary-provenance-3.1.0.md` in the source release.

The Microsoft Visual C++ Redistributable x64 is a separate system prerequisite
and is **not** included in the LogicSpace Windows packages. Install it from
[Microsoft's official download page](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)
before launching LogicSpace if it is not already installed. Do not download
individual DLLs from third-party sites.
