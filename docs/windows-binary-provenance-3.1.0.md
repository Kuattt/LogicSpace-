# LogicSpace 3.1.0 Windows binary provenance review

This is evidence for the candidate from Windows CI run
[`42625402527`](https://github.com/Kuattt/LogicSpace-/actions/runs/42625402527)
at commit `0d00daa4329978c7268456904316e10975bc3de0`.
It is **not** a certification of redistribution rights or LGPL compliance.
The later 3.1.0 build removes the Microsoft runtime DLL copies described in
this historical inventory; their presence below is **not** a description of
the final package. Recheck a final artifact if the build changes.

## Compared files

The portable ZIP passed `ZipFile.testzip()` and contains 256 entries. Its
SHA-256 is `127a731a506a4ea842c2ee0fbbccdcd9c0400343751bb16f8b7fb4813d511514`.
The installer SHA-256 is `900f0ee0f1ea5d40b2a4fd5e66e98aad12097fe3d0673a917f98c804cceaaa0d`.

We downloaded the official Windows wheels without installing them and compared
the SHA-256 of each DLL/PYD in the candidate portable ZIP with wheel members:

| Reference wheel | Wheel SHA-256 | Identical DLL/PYD files in portable ZIP |
| --- | --- | ---: |
| `pyside6_essentials-6.9.3-cp39-abi3-win_amd64.whl` | `21f98077c135864473089e59a6a0bd828e64c6644b3dd7267b102da4a2ee8f21` | 36 |
| `shiboken6-6.9.3-cp39-abi3-win_amd64.whl` | `f1498176d2d5bcade7d662e1fc5143980fb008b6c78b966289d29a4ae86cd0c6` | 5 |

The wheel metadata declares `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`.
The `opengl32sw.dll` file is among the identical wheel files. It contains
`Mesa 11.2.2` and `llvmpipe` strings; [Qt's 6.9 attribution](https://doc.qt.io/archives/qt-6.9/qt-attribution-llvmpipe.html)
describes this prebuilt DLL as Mesa llvmpipe. These strings do not establish
the exact Mesa source patches or all incorporated LLVM code.

There are 61 other DLL/PYD files in the ZIP, including the Python 3.12 runtime,
OpenSSL and Microsoft runtime files. The `python312.dll` file contains the
version string `3.12.10`. OpenSSL DLLs contain version strings `3.0.16` and
`3.5.9`; their separate build origins are not yet verified. Microsoft DLL
redistribution entitlement is not established by a file name or wheel match.
The subsequent build removes matching Microsoft runtime DLLs and requires the
official Visual C++ Redistributable x64 to be installed separately.

## Upstream source candidates, not yet proven corresponding source

Official Qt source archives were downloaded from
[`download.qt.io/archive/qt/6.9/6.9.3/submodules/`](https://download.qt.io/archive/qt/6.9/6.9.3/submodules/)
and checked against the official mirror's SHA-256 values:

| Archive | SHA-256 |
| --- | --- |
| `qtbase-everywhere-src-6.9.3.tar.xz` | `c5a1a2f660356ec081febfa782998ae5ddbc5925117e64f50e4be9cd45b8dc6e` |
| `qtimageformats-everywhere-src-6.9.3.tar.xz` | `4fb26bdbfbd4b8e480087896514e11c33aba7b6b39246547355ea340c4572ffe` |
| `qtsvg-everywhere-src-6.9.3.tar.xz` | `db76aa3358cbbe6fce7da576ff4669cb9801920188c750d3b12783bbe97026e2` |
| `pyside-setup-everywhere-src-6.9.3.tar.xz` | `7cd2d5abb98f2e6f442b0e41f5fcf930e7312ae4b17f681316b1adc7b63bb172` |

Qt's [LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations)
require complete corresponding library source (or a compliant written offer),
and the ability to install and run a modified compatible library. The source
archives above are useful references but are not yet proven to match every
binary, patch and build option in the Windows package. No written source offer
has been issued. Replacement and continued execution with modified compatible
Qt/PySide6 libraries have not been tested. These remain release gates.
