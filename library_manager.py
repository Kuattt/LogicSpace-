"""Qt dialogs for managing persistent custom components."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QTextEdit, QVBoxLayout)

from component_library import FORMAT, block_definition_from_circuit
from engine import Circuit


class SaveBlockDialog(QDialog):
    def __init__(self, library, name="", project=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save reusable component")
        self.setMinimumWidth(400)
        layout = QFormLayout(self)
        self.name = QLineEdit(name)
        layout.addRow("Name", self.name)
        self.project = QCheckBox("Save to current project")
        self.project.setChecked(project)
        self.project.setEnabled(project)
        layout.addRow(self.project)
        self.global_library = QCheckBox("Save to global library")
        self.global_library.setChecked(not project)
        layout.addRow(self.global_library)
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(library.categories())
        self.category.setCurrentText("Custom")
        layout.addRow("Category", self.category)
        self.description = QTextEdit()
        self.description.setFixedHeight(76)
        layout.addRow("Description", self.description)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Save")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self):
        if not self.name.text().strip() or not (self.project.isChecked() or self.global_library.isChecked()):
            QMessageBox.warning(self, "Choose a destination", "Enter a name and choose at least one destination.")
            return
        super().accept()


class LibraryManager(QDialog):
    def __init__(self, editor, library, parent=None):
        super().__init__(parent or editor)
        self.editor, self.library = editor, library
        self.setWindowTitle("Component Library")
        self.resize(850, 570)
        root = QVBoxLayout(self)
        heading = QHBoxLayout()
        title = QLabel("COMPONENT LIBRARY")
        title.setObjectName("overline")
        heading.addWidget(title)
        heading.addStretch()
        create = QPushButton("Create New Component")
        create.setObjectName("primary")
        create.clicked.connect(self.create_in_designer)
        heading.addWidget(create)
        root.addLayout(heading)
        filters = QHBoxLayout()
        self.category = QComboBox()
        self.category.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.category)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search components…")
        self.search.textChanged.connect(self.refresh)
        filters.addWidget(self.search, 1)
        self.favorites = QCheckBox("Favorites")
        self.favorites.toggled.connect(self.refresh)
        filters.addWidget(self.favorites)
        root.addLayout(filters)
        body = QHBoxLayout()
        self.items = QListWidget()
        self.items.currentItemChanged.connect(self.show_info)
        body.addWidget(self.items, 2)
        self.info = QTextEdit()
        self.info.setReadOnly(True)
        body.addWidget(self.info, 2)
        root.addLayout(body, 1)
        actions = QHBoxLayout()
        for label, callback in (("Use on canvas", self.use_selected),
                                ("Edit in Designer", self.edit_in_designer),
                                ("Favorite ★", self.toggle_favorite),
                                ("Rename", self.rename_component),
                                ("Duplicate", self.duplicate_component),
                                ("Delete", self.delete_component)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        root.addLayout(actions)
        actions2 = QHBoxLayout()
        for label, callback in (("New category", self.create_category),
                                ("Rename category", self.rename_category),
                                ("Add project block", self.add_project_block),
                                ("Import JSON", self.import_json),
                                ("Update from JSON", self.update_from_json),
                                ("Export JSON", self.export_json)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions2.addWidget(button)
        root.addLayout(actions2)
        self.errors = QLabel("")
        self.errors.setObjectName("error")
        self.errors.setWordWrap(True)
        root.addWidget(self.errors)
        self.refresh()

    def _report(self, callback):
        try:
            callback()
            self.editor.populate_library()
            self.refresh()
        except (OSError, ValueError, TypeError, KeyError) as error:
            QMessageBox.warning(self, "Component Library", str(error))

    def selected(self):
        item = self.items.currentItem()
        return self.library.get(item.data(Qt.UserRole)) if item else None

    def refresh(self, *_):
        previous = self.items.currentItem().data(Qt.UserRole) if self.items.currentItem() else None
        category = self.category.currentData()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("All categories", None)
        for name in self.library.categories():
            self.category.addItem(name, name)
        index = self.category.findData(category)
        self.category.setCurrentIndex(max(0, index))
        self.category.blockSignals(False)
        self.items.clear()
        for entry in self.library.list_entries(self.search.text(), self.category.currentData(), self.favorites.isChecked()):
            item = QListWidgetItem(f"{'★  ' if entry['favorite'] else ''}{entry['name']}   ·   {entry['category']}   v{entry['version']}")
            item.setData(Qt.UserRole, entry["id"])
            self.items.addItem(item)
            if entry["id"] == previous:
                self.items.setCurrentItem(item)
        if not self.items.currentItem() and self.items.count():
            self.items.setCurrentRow(0)
        _, issues = self.library.scan()
        self.errors.setText("Library warnings: " + "; ".join(issues[:3]) if issues else "")
        self.show_info()

    def show_info(self, *_):
        entry = self.selected()
        if not entry:
            self.info.setPlainText("Choose a component to preview its interface and description.")
            return
        definition = entry["definition"]
        lines = [entry["name"], "", entry["description"] or "No description", "",
                 f"Category: {entry['category']}", f"Version: {entry['version']}",
                 f"ID: {entry['id']}", f"Created: {entry['created']}",
                 f"Modified: {entry['modified']}", "",
                 "Inputs: " + ", ".join(definition["inputs"]),
                 "Outputs: " + ", ".join(definition["outputs"]),
                 f"Internal components: {len(definition['circuit']['components'])}"]
        self.info.setPlainText("\n".join(lines))

    def use_selected(self):
        entry = self.selected()
        if entry:
            self.editor.set_tool(None)
            self.editor.pending_kind = "LIB:" + entry["id"]
            self.editor.set_status(f"Click canvas to place {entry['name']}")
            self.accept()

    def create_in_designer(self):
        self.editor.new_block_designer()
        self.accept()

    def edit_in_designer(self):
        entry = self.selected()
        if entry and self.editor.open_library_designer(entry["id"]):
            self.accept()

    def toggle_favorite(self):
        entry = self.selected()
        if entry:
            self._report(lambda: self.library.update(entry["id"], favorite=not entry["favorite"]))

    def rename_component(self):
        entry = self.selected()
        if not entry: return
        name, ok = QInputDialog.getText(self, "Rename component", "Name", text=entry["name"])
        if ok:
            self._report(lambda: self.library.update(entry["id"], name=name))

    def duplicate_component(self):
        entry = self.selected()
        if not entry: return
        name, ok = QInputDialog.getText(self, "Duplicate component", "New name", text=entry["name"] + " Copy")
        if ok:
            self._report(lambda: self.library.duplicate(entry["id"], name))

    def delete_component(self):
        entry = self.selected()
        if entry and QMessageBox.question(self, "Delete component", f"Delete {entry['name']} from the global library?\nExisting projects keep their copies.",
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self._report(lambda: self.library.delete(entry["id"]))

    def create_category(self):
        name, ok = QInputDialog.getText(self, "New category", "Name")
        if ok:
            self._report(lambda: self.library.create_category(name))

    def rename_category(self):
        old = self.category.currentData()
        if not old:
            QMessageBox.information(self, "Category", "Choose a category first.")
            return
        name, ok = QInputDialog.getText(self, "Rename category", "New name", text=old)
        if ok:
            self._report(lambda: self.library.rename_category(old, name))

    def add_project_block(self):
        names = sorted(self.editor.circuit.blocks)
        if not names:
            QMessageBox.information(self, "Project blocks", "This project has no custom blocks yet.")
            return
        name, ok = QInputDialog.getItem(self, "Add project block", "Block", names, 0, False)
        if not ok: return
        dialog = SaveBlockDialog(self.library, name, project=False, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self._report(lambda: self.library.save(dialog.name.text(), self.editor.circuit.blocks[name],
                                                  dialog.category.currentText(), dialog.description.toPlainText()))

    def import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import component", "", "LogicSpace JSON (*.json)")
        if path:
            self._report(lambda: self.library.import_json(path))

    def update_from_json(self):
        entry = self.selected()
        if not entry: return
        path, _ = QFileDialog.getOpenFileName(self, "Update definition", "", "LogicSpace JSON (*.json)")
        if not path: return
        def update():
            import json
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            definition = (data["definition"] if data.get("format") == FORMAT else
                          block_definition_from_circuit(Circuit.from_dict(data)) if data.get("format") == "logicspace" else data)
            self.library.update(entry["id"], definition=definition)
        self._report(update)

    def export_json(self):
        entry = self.selected()
        if not entry: return
        path, _ = QFileDialog.getSaveFileName(self, "Export component", entry["name"] + ".json", "LogicSpace JSON (*.json)")
        if path:
            self._report(lambda: self.library.export(entry["id"], path if path.endswith(".json") else path + ".json"))
