# LogicSpace 3.1.0 — Release candidate

**Unpublished preparation notes.** The latest public release remains [v3.0.0](https://github.com/Kuattt/LogicSpace-/releases/tag/v3.0.0). Do not present the assets below as public downloads before a checked 3.1.0 release exists.

## What's new

- Windows 10/11 x64 packages: a per-user graphical installer and a portable ZIP, built from the same LogicSpace application as the Ubuntu/Linux source distribution.
- Windows user data is stored under `%LOCALAPPDATA%\LogicSpace`, outside the installation folder. The uninstaller leaves projects and settings in place.
- Native Windows CI builds both packages and checks Python tests, SHA-256, offscreen startup, reinstall and uninstall.
- Release packages now include the existing draft LogicSpace license, the informational commercial-licensing draft, third-party notices and supporting license texts. These drafts are not represented as an approved legal agreement.
- The existing Ubuntu/Linux source installation, simulator, CPU/Assembly, HDL subset and debugging tools remain available.

## Installation

**Windows:** after publication, download `LogicSpace-Setup.exe` from the 3.1.0 GitHub Release and follow the installer, or download `LogicSpace-Windows-x64.zip`, extract the whole archive and run `LogicSpace/LogicSpace.exe`. No separate Python installation is required. Packages are unsigned; keep Windows security protections enabled.

**Ubuntu 24.04+:** download the source ZIP from the same release, extract it to a directory you own, then run `./install.sh` and `./launch.sh`. Python 3.12+ and a graphical session are required. Minimal installations may need the `libegl1` system package.

Verify downloads with the release's `SHA256SUMS.txt`. The [website](https://logicspace.pages.dev/) and [detailed guide](https://github.com/Kuattt/LogicSpace-/blob/main/docs/detailed-guide.md) provide further instructions.

## Known limitations and release gates

- Windows CI uses Qt offscreen startup checks. The installer wizard, desktop shortcuts, interactive circuit editing, Defender/SmartScreen behavior and real Windows 10/11 sessions still need manual review.
- External Icarus, Yosys and Verilator execution requires Linux Bubblewrap and is unavailable on Windows. Internal HDL editing, import/export and LogicSpace simulation remain available.
- HDL covers a documented subset. FPGA export does not synthesize or program hardware. Simulation steps are logical, not physical time.
- Automatic in-place updates are unavailable for source checkouts and Windows packages; the app opens the official release page for manual updates.
- Public distribution of Windows bundles requires a completed review of PySide6/Qt and bundled third-party notices, source availability obligations and resource provenance. The author accepted the exact proposed LogicSpace license text for original materials they own, but the document remains explicitly marked as a draft for legal review; rights to all included assets are not established. These proposed terms are not retroactive to v3.0.0.
