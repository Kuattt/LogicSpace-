"""Non-blocking release notifications for source-based LogicSpace installs."""
from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QTextEdit,
                               QVBoxLayout)

from update_model import (UpdateSettings, find_update,
                          update_destination)
from version import APP_VERSION, RELEASES_URL


class CheckWorker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, settings, include_prerelease, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.include_prerelease = include_prerelease

    def run(self):
        try:
            self.settings.checked()  # Count failed attempts toward the daily limit.
            self.result.emit(find_update(include_prerelease=self.include_prerelease))
        except (ValueError, OSError) as error:
            self.failed.emit(str(error))


class UpdateDialog(QDialog):
    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release = release
        self.setWindowTitle("LogicSpace Update Available")
        self.resize(510, 390)
        box = QVBoxLayout(self)
        title = QLabel(f"LogicSpace {release.tag} is available")
        title.setStyleSheet("font-size: 17pt; font-weight: 600; color: #e7edf7")
        box.addWidget(title)
        box.addWidget(QLabel(f"Current: {APP_VERSION}  ·  New: {release.tag}"))
        notes = QTextEdit()
        notes.setReadOnly(True)
        notes.setPlainText(release.notes or "See the official release page for changes.")
        box.addWidget(notes, 1)
        notice = QLabel("This source installation is not replaced automatically. Update Now opens the official GitHub release for a verified manual download.")
        notice.setWordWrap(True)
        box.addWidget(notice)
        row = QHBoxLayout()
        for label, callback in (("Update Now", self.open_release),
                                ("Maybe Later", self.reject),
                                ("View Release Notes", self.open_release)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        box.addLayout(row)

    def open_release(self):
        if QDesktopServices.openUrl(QUrl(update_destination(self.release))):
            self.accept()
        else:
            QMessageBox.warning(self, "Open release", "Could not open the official release page in a browser.")


class UpdateSettingsDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Update Settings")
        self.resize(430, 260)
        data = controller.settings.load()
        box = QVBoxLayout(self)
        box.addWidget(QLabel(f"Current version: {APP_VERSION}"))
        checked = data["last_checked"]
        box.addWidget(QLabel("Last update check: " + (checked or "Never")))
        self.automatic = QCheckBox("Automatically check once per day")
        self.automatic.setChecked(data["auto_check"])
        box.addWidget(self.automatic)
        self.beta = QCheckBox("Include prerelease updates")
        self.beta.setChecked(data["include_prerelease"])
        box.addWidget(self.beta)
        notice = QLabel("Updates are downloaded manually from the official GitHub release page. Existing projects and libraries are not changed by a check.")
        notice.setWordWrap(True); box.addWidget(notice)
        history = QPushButton("View Release History")
        history.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)))
        box.addWidget(history)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def save(self):
        data = self.controller.settings.load()
        data["auto_check"] = self.automatic.isChecked()
        data["include_prerelease"] = self.beta.isChecked()
        try: self.controller.settings.save(data)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Update Settings", str(error)); return
        self.accept()


class UpdateController:
    def __init__(self, editor, settings=None):
        self.editor = editor
        self.settings = settings or UpdateSettings()
        self.worker = None
        self.manual = False

    def schedule_startup(self):
        QTimer.singleShot(5000, self._startup)

    def _startup(self):
        if not self.editor.isVisible(): return
        try:
            if self.settings.due(): self._start(False)
        except (OSError, ValueError) as error:
            self.editor.set_status(f"Update settings: {error}")

    def manual_check(self):
        self._start(True)

    def _start(self, manual):
        if self.worker is not None and self.worker.isRunning(): return
        try: include_beta = self.settings.load()["include_prerelease"]
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.editor, "Update Settings", str(error)); return
        self.manual = manual
        self.worker = CheckWorker(self.settings, include_beta, self.editor)
        self.worker.result.connect(self._result)
        self.worker.failed.connect(self._failed)
        self.worker.start()
        if manual: self.editor.set_status("Checking official GitHub Releases…")

    def _result(self, release):
        if not self.editor.isVisible(): return
        if release is None:
            if self.manual: self.editor.set_status(f"LogicSpace {APP_VERSION} is up to date")
            return
        UpdateDialog(release, self.editor).exec()

    def _failed(self, message):
        if self.manual and self.editor.isVisible():
            QMessageBox.information(self.editor, "Update Check", message)
        elif self.editor.isVisible():
            self.editor.set_status("Update check unavailable; try Settings → Check for Updates later")

    def show_settings(self):
        try: UpdateSettingsDialog(self, self.editor).exec()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.editor, "Update Settings", str(error))

    def stop(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(4000)
