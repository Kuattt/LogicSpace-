# LogicSpace 3.1.0 — third-party notices and release inventory (draft)

**Release review document, not a certificate of license compliance.** It describes
the proposed Linux source ZIP and the Windows x64 installer/portable ZIP. The
Windows binaries inspected were CI candidates, not published 3.1.0 assets.
The final binary inventory and its SHA-256 hashes must be checked again after
the licensing files are included and the Windows packages are rebuilt.

The [LogicSpace license](LICENSE.md) concerns only original LogicSpace
materials to the extent the rights holder can license them. It does not
relicense the components below. That document is currently a **draft**.

## Components and applicable materials

| Component | Distribution in the proposed packages | License information and official source | Release action |
| --- | --- | --- | --- |
| Python 3.12 runtime | Windows package contains `python312.dll`, `python3.dll`, extension modules and standard library files; Linux source ZIP does not bundle Python. Exact Windows patch/build provenance still needs verification. | Python Software Foundation License Version 2 and incorporated-software notices: [Python 3.12 license](https://docs.python.org/3.12/license.html); a copy of the upstream 3.12-branch `LICENSE` is in [`licenses/Python-3.12.txt`](licenses/Python-3.12.txt). | Match the license and incorporated-software notices to the **exact** Python build in final CI. |
| PySide6-Essentials 6.9.3 and shiboken6 6.9.3 | Bundled in Windows; on Linux, `install.sh` installs `PySide6-Essentials>=6.7,<7` when needed, so the installed version can differ. The inspected Windows CI portable package contains 36 DLL/PYD files byte-identical to the PySide6-Essentials 6.9.3 Windows wheel and 5 byte-identical to the shiboken6 6.9.3 Windows wheel; see [binary provenance](docs/windows-binary-provenance-3.1.0.md). | Wheel metadata states `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`; [Qt for Python licensing](https://doc.qt.io/qtforpython-6/), [package contents](https://doc.qt.io/qtforpython-6/package_details.html), [third-party licenses](https://doc.qt.io/qtforpython-6/licenses.html). Full LGPLv3 and GPLv3 texts are in [`licenses/`](licenses/). | Complete the applicable LGPLv3 source/access and modified-library replacement review. |
| Qt 6.9.3 | The Windows candidate includes `Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Widgets.dll`, `Qt6Network.dll`, `Qt6Svg.dll` and Qt plugins. Linux source ZIP has no Qt binaries. | [Qt 6.9 licensing](https://doc.qt.io/archives/qt-6.9/licensing.html), [Qt 6.9.3 third-party code](https://doc.qt.io/archives/qt-6.9/licenses-used-in-qt.html), [Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations). The package now includes an [overinclusive appendix of 51 official Qt 6.9.3 attribution texts](licenses/Qt-6.9.3-attributions.txt) for the Core, GUI, Image Formats, Network and SVG module groups. | Match the **shipped** modules/plugins to Qt's exact build SBOM and confirm applicable notices and library source/access terms. This appendix does not establish which items were compiled into the wheel. |
| OpenSSL 3 | Four `libcrypto-3*.dll` / `libssl-3*.dll` files occur in the Windows CI candidate; no OpenSSL binary is bundled in the Linux source ZIP. Exact patch versions and file origins are unverified. | OpenSSL 3 uses Apache License 2.0: [OpenSSL license](https://openssl-library.org/source/license/index.html); text in [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt). | Identify the exact DLL builds and collect any applicable upstream notices and source provenance. |
| Microsoft Visual C++ Runtime and Windows API-set/UCRT DLLs | The Windows CI candidate contains `MSVCP140*.dll`, `VCRUNTIME140*.dll`, `ucrtbase.dll` and `api-ms-win-*.dll` at several paths. No Microsoft binaries are in the Linux source ZIP. | Redistribution depends on the actual build provenance and applicable Microsoft terms: [Visual Studio redistribution list](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution), [Microsoft local deployment guidance](https://learn.microsoft.com/en-us/cpp/windows/choosing-a-deployment-method?view=msvc-170). | **UNKNOWN:** document the source, version and redistribution entitlement for each exact DLL before publication; do not infer permission from filenames. |
| Software OpenGL runtime | `PySide6/opengl32sw.dll` is bundled in the Windows candidate and is byte-identical to the file in the PySide6-Essentials 6.9.3 Windows wheel. Its binary contains `Mesa 11.2.2` and `llvmpipe` strings. This identifies its likely implementation, but not a complete build provenance. | [Qt 6.9 identifies the prebuilt Windows software OpenGL DLL as Mesa llvmpipe](https://doc.qt.io/archives/qt-6.9/qt-attribution-llvmpipe.html) and lists MIT and Boost Software License 1.0 notices; the [attribution text](licenses/Mesa-llvmpipe-attribution.txt) is included in the package. | Verify the exact Mesa/LLVM source and build provenance and all applicable notices before publication. |
| PyInstaller 6.22.3 bootloader | Used to build `LogicSpace.exe` in the Windows package; the build tool itself is not shipped. | [PyInstaller license and bootloader exception](https://pyinstaller.org/en/stable/license.html). The published exception permits applications built with PyInstaller under their own terms, subject to dependency licenses. | Confirm the final build uses the pinned version and no modified PyInstaller bootloader. |
| NSIS installer stub | `LogicSpace-Setup.exe` is built using NSIS; the full NSIS build tool is not shipped. | **UNKNOWN for the exact CI-installed NSIS package and installer stub.** | Record the NSIS version, origin and applicable installer-stub notices in final CI. |
| External HDL tools | Icarus Verilog, Yosys, Verilator, GTKWave and Bubblewrap are optional system tools; they are not included in the Windows or Linux source packages. | Their own licenses remain applicable to separately installed copies. | Re-audit if any tool is later bundled. |

The Windows candidate contains additional Qt image/platform/TLS plugins and
Python extension modules. Qt and Python have further incorporated material;
the links above identify the upstream inventories, **not** a completed
file-by-file mapping of the final package. The package must not be described
as fully cleared until that mapping and required notices are complete.

## LogicSpace assets needing rights confirmation

- Application icons: `resources/logicspace.svg` and `resources/logicspace.png`.
- Screenshots: `docs/screenshots/workspace.png` and `docs/screenshots/hdl-editor.png`.
- Example circuits, Assembly, machine-code images and HDL under `examples/`.
- Original application code, documentation and any adapted or contributed snippets.

The project history alone does not establish exclusive rights to every asset.
See [the rights-review checklist](docs/licensing-review-3.1.0.md) before
approving the LogicSpace license for the new release.

## LGPLv3 review before Windows publication

The proposed proprietary LogicSpace terms must not restrict rights in the
separately licensed Qt/PySide6 libraries. The Windows build uses separate
DLLs/PYD files, but actual replacement and continued execution with a
compatible modified library still require a practical test. The final
distribution also needs the appropriate notices, license texts, complete
corresponding library source or compliant offer, and any installation
information required by the applicable LGPLv3 terms. This document does
not claim these obligations are already satisfied.

The `licenses/` copies are provided for review and distribution preparation;
they are **not** the LogicSpace project license. The GNU and Apache texts were
copied from Ubuntu's standard `common-licenses` files; the Python text was
retrieved from the official CPython 3.12 branch. Exact final binary provenance
remains a release gate.
