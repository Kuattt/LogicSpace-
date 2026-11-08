# LogicSpace 3.1.0 release readiness (working checklist)

This is a technical and legal-review checklist, **not a license or legal opinion**. It does not amend v3.0.0, grant commercial rights or certify compliance. The 3.1.0 candidate must not be published until the items below are resolved and the final artifacts are verified.

## Verified technical baseline

- The published v3.0.0 tag remains unchanged. `windows-support` was based on that tag; its native Windows 2022 CI run [42503815048](https://github.com/Kuattt/LogicSpace-/actions/runs/42503815048) passed 337 tests with one POSIX-only skip and produced an installer and portable ZIP. It used offscreen GUI startup and silent installer checks, not interactive Windows 10/11 use.
- The 3.1.0 candidate uses the existing simulator and retains Linux source installation. The candidate needs its own Linux and Windows CI runs after the final version, notices and packaging are fixed.
- No Linux `.deb` or AppImage has been built or verified. A source ZIP remains the planned Linux distribution.

## Distribution blockers

1. **LogicSpace rights and terms.** The v3.0.0 source ZIP included no project license. Local `LICENSE.md` and `COMMERCIAL-LICENSE.md` are expressly drafts. Confirm the actual rights holder, rights to contributions, intended permissions and start date with qualified counsel in Kazakhstan. Do not apply new terms retroactively to v3.0.0 or suggest that a repository license cancels rights granted by GitHub's public-repository terms.
2. **Windows PySide6/Qt bundle.** The checked Windows CI archive includes PySide6 6.9.3, Qt DLLs and `qwindows.dll`, but contains no file named LICENSE, NOTICE or COPYRIGHT. The selected LGPLv3 route, if used, needs a prominent notice, applicable license texts, corresponding library source or a compliant offer, and a way for users to use a modified compatible library. Qt also includes separately licensed third-party material. Package contents and exact obligations need review before distribution. [Qt's LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations), [Qt for Python package details](https://doc.qt.io/qtforpython-6/package_details.html), [Qt for Python licensing](https://doc.qt.io/qtforpython-6/).
3. **Other bundled binaries.** The native Windows CI portable ZIP has 45 more files than the earlier Wine-built ZIP, including Windows API-set/UCRT and OpenSSL DLLs. Identify origins, versions, redistribution rights and required notices for each exact release bundle. Do not infer the license of a DLL from its filename.
4. **Project resources and examples.** The provenance of the app icon, screenshots and HDL/Assembly/JSON examples is not documented sufficiently to establish all distribution rights. Review source history and any third-party assets before extending a proprietary license to them.
5. **Interactive Windows verification.** Check the installer wizard, Start menu and optional desktop shortcut, non-admin install, actual GUI editing/simulation, save/reopen, uninstall and data preservation on Windows 10 and 11 x64. Check Defender/SmartScreen behavior without bypassing protection.
6. **Final artifact identity.** After approval, build 3.1.0 on native Windows CI, verify installer/ZIP SHA-256 and contents, build the matching 3.1.0 Linux source ZIP, then publish one `SHA256SUMS.txt`. Do not relabel or re-upload the earlier 3.0.0-based Windows assets as 3.1.0.

## Decisions for the owner and Kazakhstan counsel

- Who owns the code, logo, screenshots, examples and contributions, and which evidence supports that chain of rights?
- Which exact source-available permission is intended for individual use, local modification, public forks, teaching, organizations and commercial use? When would it begin, and how will users of v3.0.0 be distinguished from later recipients?
- Will the Windows bundle use LGPLv3-compliant PySide6/Qt distribution or separately acquired commercial Qt packages? Who will provide the exact third-party notices, source materials and replacement instructions?
- Which terms, contact route and signatory would a future commercial agreement use? The current draft notice grants no commercial rights.
- Are the included Microsoft runtime, OpenSSL, icon and example materials cleared for this exact distribution?
- Is the unsigned Windows package and its remaining manual-test coverage acceptable for an initial public beta, or should Windows publication wait?

## Publication gate

Keep the candidate branch and tests available for review. Do not merge it to `main`, create `v3.1.0`, upload GitHub Release files, or update the public download page until the owner has reviewed the concrete terms and artifact inventory and the required legal and platform checks are complete.
