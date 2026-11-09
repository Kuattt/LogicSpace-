# LogicSpace 3.1.0 — Linux and Windows

This release extends the existing LogicSpace desktop application to Windows 10/11 x64 while keeping the Ubuntu/Linux source installation. The earlier [v3.0.0](https://github.com/Kuattt/LogicSpace-/releases/tag/v3.0.0) remains unchanged.

## What's new

- Windows 10/11 x64 packages: a per-user graphical installer and a portable ZIP, built from the same LogicSpace application as the Ubuntu/Linux source distribution.
- Windows user data is stored under `%LOCALAPPDATA%\LogicSpace`, outside the installation folder. The uninstaller leaves projects and settings in place.
- Native Windows CI builds both packages and checks Python tests, SHA-256, offscreen startup, reinstall and uninstall.
- Release packages include the author-accepted LogicSpace license text, still marked for legal review, the informational commercial-licensing draft, third-party notices and supporting license texts. They are not represented as a signed commercial agreement.
- The existing Ubuntu/Linux source installation, simulator, CPU/Assembly, HDL subset and debugging tools remain available.

## Installation

**Windows:** after publication, download `LogicSpace-Setup.exe` from the 3.1.0 GitHub Release and follow the installer, or download `LogicSpace-Windows-x64.zip`, extract the whole archive and run `LogicSpace/LogicSpace.exe`. No separate Python installation is required. Packages are unsigned; keep Windows security protections enabled.

Install the [Microsoft Visual C++ Redistributable x64](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) separately if it is not already present. The Windows packages do not contain Microsoft runtime DLLs. The same release includes `Qt-sources-6.9.3.zip` and [Qt/PySide6 replacement instructions](docs/qt-source-and-replacement-3.1.0.md).

**Ubuntu 24.04+:** download the source ZIP from the same release, extract it to a directory you own, then run `./install.sh` and `./launch.sh`. Python 3.12+ and a graphical session are required. Minimal installations may need the `libegl1` system package.

Verify downloads with the release's `SHA256SUMS.txt`. The [website](https://logicspace.pages.dev/) and [detailed guide](https://github.com/Kuattt/LogicSpace-/blob/main/docs/detailed-guide.md) provide further instructions.

## Known limitations

- Windows CI uses Qt offscreen startup checks. The installer wizard, desktop shortcuts, interactive circuit editing, Defender/SmartScreen behavior and real Windows 10/11 sessions still need manual review.
- External Icarus, Yosys and Verilator execution requires Linux Bubblewrap and is unavailable on Windows. Internal HDL editing, import/export and LogicSpace simulation remain available.
- HDL covers a documented subset. FPGA export does not synthesize or program hardware. Simulation steps are logical, not physical time.
- Automatic in-place updates are unavailable for source checkouts and Windows packages; the app opens the official release page for manual updates.
- The author accepted the existing LogicSpace license text for original materials they own. It remains marked as a draft for legal review; rights to every included asset have not been independently established. Its terms are not retroactive to v3.0.0. Qt/PySide6 and other third-party components retain their own licenses.
