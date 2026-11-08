LogicSpace 3.1.0 Windows x64 build
==================================

Build on Windows 10/11 x64 with 64-bit Python 3.12 and NSIS 3 installed.

  py -3.12 -m venv .venv
  .venv\Scripts\python.exe -m pip install -r windows\requirements-build.txt
  .venv\Scripts\python.exe -m unittest discover -s tests -q
  .venv\Scripts\python.exe windows\build.py

The build writes dist\windows\LogicSpace-Windows-x64.zip,
LogicSpace-Setup.exe, SHA256SUMS.txt and README-Windows.txt. Both packages use
the same PyInstaller onedir stage under build\windows\dist\LogicSpace.

The installer is per-user and uses HKCU; no administrator rights are requested.
Its uninstaller removes only the files in the build manifest. Projects and
settings are stored outside the installation directory under LocalAppData.

The GitHub workflow at .github/workflows/windows-build.yml runs native Windows
tests and packaging on pushes to windows-support. It can also be dispatched
manually. Check its test and smoke-test results before distribution.

External Icarus, Yosys and Verilator execution uses the Linux Bubblewrap
sandbox in the current application and is therefore disabled on Windows.
Internal HDL parsing, import/export, vector tests and LogicSpace simulation
still work. GTKWave can open VCD files when installed separately.

The executables are not code signed. A release requires Windows 10/11 GUI
testing, installer uninstall/reinstall testing and a review of third-party
license notices before public distribution.
