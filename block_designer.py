"""Dedicated custom-block workspace reusing the LogicSpace Editor canvas."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QAction, QKeySequence
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QSpinBox, QComboBox, QTextEdit, QTabWidget,
                               QVBoxLayout, QWidget, QColorDialog)

from block_visuals import block_geometry, paint_designed_block, terminal_positions
from component_library import _atomic_json
from designer_model import DesignerModel, SIDES
from engine import Circuit, Simulator, bit_width
from library_manager import SaveBlockDialog
from main import Editor


class BlockPreview(QWidget):
    def __init__(self, model, draft=None, parent=None, spec_provider=None):
        super().__init__(parent)
        self.model, self.draft, self.spec_provider = model, draft, spec_provider
        self.setMinimumHeight(170)

    def paintEvent(self, event):
        spec = self.spec_provider() if self.spec_provider else self.model.preview_spec()
        if self.draft:
            spec["designer"]["appearance"].update(self.draft())
        width, height = block_geometry(spec)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#11151c"))
        scale = min((self.width() - 28) / (width + 25), (self.height() - 20) / (height + 25))
        painter.translate((self.width() - width * scale) / 2, (self.height() - height * scale) / 2)
        painter.scale(scale, scale)
        positions = terminal_positions(spec, width, height)
        paint_designed_block(painter, spec, self.model.name, width, height, positions)
        painter.setPen(QPen(QColor("#9acaff"), 2.3))
        painter.setBrush(QColor("#11151c"))
        for point, _ in positions.values():
            painter.drawEllipse(point, 5, 5)
        painter.end()


class TestComponentDialog(QDialog):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle("Test Component")
        self.setMinimumWidth(440)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.controls = {}
        for terminal in model.terminals():
            if terminal.kind != "INPUT": continue
            width = bit_width(terminal)
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            value = QSpinBox()
            value.setRange(0, (1 << width) - 1)
            value.setValue(int(terminal.params.get("value") or 0) & ((1 << width) - 1))
            unknown = QPushButton("X")
            unknown.setCheckable(True)
            unknown.setToolTip("Use unknown input value")
            line.addWidget(value, 1)
            line.addWidget(unknown)
            form.addRow(f"{terminal.params.get('label', 'Input')} ({width}b)", row)
            self.controls[terminal.id] = (terminal, value, unknown)
        self.steps = QSpinBox()
        self.steps.setRange(0, 1000)
        form.addRow("Simulation steps", self.steps)
        root.addLayout(form)
        run = QPushButton("Run Test")
        run.setObjectName("primary")
        run.clicked.connect(self.run_test)
        root.addWidget(run)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(150)
        root.addWidget(self.result)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.run_test()

    def run_test(self):
        values = {}
        for terminal, control, unknown in self.controls.values():
            width = bit_width(terminal)
            for bit in range(width):
                external = terminal.params["label"] if width == 1 else terminal.params["label"] + str(bit)
                values[external] = None if unknown.isChecked() else (control.value() >> bit) & 1
        try:
            outputs = self.model.test(values, self.steps.value())
            lines = ["INPUTS"]
            for terminal, control, unknown in self.controls.values():
                lines.append(f"  {terminal.params['label']} = {'X' if unknown.isChecked() else format(control.value(), f'0{bit_width(terminal)}b')}")
            lines += ["", "OUTPUTS"]
            for terminal in self.model.terminals():
                if terminal.kind != "OUTPUT": continue
                width = bit_width(terminal)
                bits = [outputs[terminal.params["label"] if width == 1 else terminal.params["label"] + str(i)]
                        for i in range(width)]
                lines.append(f"  {terminal.params['label']} = {''.join('X' if v is None else str(v) for v in reversed(bits))}")
            self.result.setPlainText("\n".join(lines))
        except (ValueError, TypeError, KeyError) as error:
            self.result.setPlainText("Cannot test component:\n" + str(error))


class BlockDesigner(Editor):
    def __init__(self, parent_editor, *, circuit=None, definition=None, name=None, entry=None):
        self.parent_editor = parent_editor
        super().__init__()
        # Project-wide navigation belongs to the main editor. The designer
        # keeps its focused Components / Tools / Terminals workflow.
        self.sidebar_tabs.removeTab(1)
        if entry:
            self.model = DesignerModel.from_definition(entry["definition"], entry["name"],
                                                       description=entry["description"], category=entry["category"],
                                                       library_id=entry["id"], version=entry["version"])
        elif definition is not None:
            self.model = DesignerModel.from_definition(definition, name or "Custom Block")
        else:
            self.model = DesignerModel(circuit, name=name or "New Component")
        self.circuit = self.model.circuit
        self.sim = Simulator(self.circuit)
        self.global_library = parent_editor.global_library
        self.populate_library()
        self._build_designer_ui()
        self.render()
        self.refresh_terminals()
        self.load_appearance()
        self.dirty = False
        self.history.clear()
        self.future.clear()
        self._title()
        self.resize(1500, 930)

    def render(self):
        if hasattr(self, "model"):
            self.model.ensure_terminal_metadata()
        super().render()
        if hasattr(self, "terminal_list") and hasattr(self, "live_preview"):
            self.refresh_terminals()

    def _title(self):
        name = self.model.name if hasattr(self, "model") else "Custom Block"
        self.setWindowTitle(f"LogicSpace — Block Designer — {name}" + (" •" if self.dirty else ""))

    def _build_designer_ui(self):
        for action in list(self.actions()):
            self.removeAction(action)
        self.menuBar().clear()
        menu = self.menuBar().addMenu("Designer")
        edit = self.menuBar().addMenu("Edit")
        for target, label, shortcut, callback in (
                (menu, "Save…", "Ctrl+S", self.save), (menu, "Save As…", "Ctrl+Shift+S", self.save_as_component),
                (menu, "Export JSON…", None, self.export_definition),
                (menu, "Run Test…", "F5", self.run_test_dialog), (menu, "Preview…", None, self.show_preview),
                (edit, "Undo", "Ctrl+Z", self.undo), (edit, "Redo", "Ctrl+Shift+Z", self.redo),
                (edit, "Copy", "Ctrl+C", self.copy), (edit, "Paste", "Ctrl+V", self.paste),
                (edit, "Duplicate", "Ctrl+D", self.duplicate), (edit, "Delete", "Delete", self.delete_selected)):
            action = QAction(label, self)
            if shortcut: action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            target.addAction(action)
            self.addAction(action)
        # The existing editor canvas, component list and inspector remain live.
        self.centralWidget().layout().itemAt(0).widget().hide()
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(18, 6, 18, 6)
        title = QLabel("CUSTOM BLOCK DESIGNER")
        title.setObjectName("overline")
        bar.addWidget(title)
        bar.addStretch()
        for label, callback in (("Undo", self.undo), ("Redo", self.redo),
                                ("Preview", self.show_preview), ("Run Test", self.run_test_dialog),
                                ("Component Settings", lambda: self.designer_tabs.setCurrentIndex(1)),
                                ("Save As", self.save_as_component), ("Save", self.save)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            if label == "Save": button.setObjectName("primary")
            bar.addWidget(button)
        self.centralWidget().layout().insertWidget(1, toolbar)
        self.content_splitter.setSizes([250, 850, 350])
        tabs = QTabWidget()
        tabs.setObjectName("sidebarTabs")
        self.designer_tabs = tabs
        self.inspector_layout.removeWidget(self.config_panel)
        tabs.addTab(self._terminal_page(), "Terminals")
        tabs.addTab(self._appearance_page(), "Appearance")
        tabs.addTab(self.config_panel, "Element")
        self.inspector_layout.insertWidget(3, tabs, 1)
        tabs.currentChanged.connect(self._sync_element_tab)
        self._sync_element_tab()
        self.sidebar_tabs.setCurrentIndex(0)

    def selection_changed(self):
        super().selection_changed()
        if hasattr(self, "designer_tabs"):
            self._sync_element_tab()

    def _sync_element_tab(self, *_):
        self.config_panel.setVisible(self.designer_tabs.currentIndex() == 2 and bool(self.inspector_component_id))

    def _terminal_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(5, 8, 5, 5)
        self.terminal_list = QListWidget()
        self.terminal_list.setMaximumHeight(190)
        self.terminal_list.currentItemChanged.connect(self.show_terminal)
        layout.addWidget(self.terminal_list)
        buttons = QHBoxLayout()
        for label, direction in (("+ Input", "INPUT"), ("+ Output", "OUTPUT")):
            button = QPushButton(label)
            button.clicked.connect(lambda _, kind=direction: self.add_terminal(kind))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        form = QFormLayout()
        self.term_name = QLineEdit()
        self.term_width = QSpinBox(); self.term_width.setRange(1, 8)
        self.term_side = QComboBox(); self.term_side.addItems(SIDES)
        self.term_order = QSpinBox(); self.term_order.setRange(0, 99)
        self.term_description = QLineEdit()
        for title, control in (("Name", self.term_name), ("Bits", self.term_width),
                               ("Side", self.term_side), ("Order", self.term_order),
                               ("Description", self.term_description)):
            form.addRow(title, control)
        layout.addLayout(form)
        actions = QHBoxLayout()
        apply = QPushButton("Apply terminal")
        apply.setObjectName("primary")
        apply.clicked.connect(self.apply_terminal)
        remove = QPushButton("Remove")
        remove.clicked.connect(self.remove_terminal)
        actions.addWidget(apply); actions.addWidget(remove)
        layout.addLayout(actions)
        self.terminal_preview = BlockPreview(self.model, spec_provider=self.terminal_draft_spec)
        layout.addWidget(self.terminal_preview)
        for signal in (self.term_name.textChanged, self.term_width.valueChanged,
                       self.term_side.currentTextChanged, self.term_order.valueChanged,
                       self.term_description.textChanged):
            signal.connect(self.terminal_preview.update)
        hint = QLabel("INPUT and OUTPUT elements are real internal terminals. Wire their pins on the canvas.")
        hint.setWordWrap(True); hint.setObjectName("hint")
        layout.addWidget(hint)
        return page

    def _appearance_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(5, 8, 5, 5)
        form = QFormLayout()
        self.name_field = QLineEdit()
        self.category_field = QComboBox(); self.category_field.setEditable(True)
        self.category_field.addItems(self.global_library.categories())
        self.description_field = QTextEdit(); self.description_field.setFixedHeight(56)
        self.color_field = QLineEdit()
        color_picker = QPushButton("Choose color…")
        color_picker.clicked.connect(self.choose_color)
        self.width_field = QSpinBox(); self.width_field.setRange(100, 520)
        self.height_field = QSpinBox(); self.height_field.setRange(100, 520)
        self.label_field = QLineEdit()
        self.short_field = QLineEdit()
        for label, widget in (("Name", self.name_field), ("Category", self.category_field),
                              ("Description", self.description_field), ("Body color", self.color_field),
                              ("", color_picker), ("Width", self.width_field), ("Height", self.height_field),
                              ("Display label", self.label_field), ("Short text", self.short_field)):
            form.addRow(label, widget)
        layout.addLayout(form)
        apply = QPushButton("Apply appearance")
        apply.setObjectName("primary")
        apply.clicked.connect(self.apply_appearance)
        layout.addWidget(apply)
        self.live_preview = BlockPreview(self.model, self.appearance_draft)
        layout.addWidget(self.live_preview)
        layout.addStretch()
        for widget, signal in ((self.name_field, self.name_field.textChanged),
                               (self.color_field, self.color_field.textChanged),
                               (self.width_field, self.width_field.valueChanged),
                               (self.height_field, self.height_field.valueChanged),
                               (self.label_field, self.label_field.textChanged),
                               (self.short_field, self.short_field.textChanged)):
            signal.connect(self.live_preview.update)
        return page

    def selected_terminal(self):
        item = self.terminal_list.currentItem()
        return self.circuit.components.get(item.data(Qt.UserRole)) if item else None

    def terminal_draft_spec(self):
        spec = self.model.preview_spec()
        terminal = self.selected_terminal()
        if terminal is None:
            return spec
        key = "inputs" if terminal.kind == "INPUT" else "outputs"
        old_width = bit_width(terminal)
        old_label = terminal.params.get("label", "")
        old_names = [old_label if old_width == 1 else f"{old_label}{bit}"
                     for bit in range(old_width)]
        new_width = self.term_width.value()
        new_label = self.term_name.text().strip() or "?"
        new_names = [new_label if new_width == 1 else f"{new_label}{bit}"
                     for bit in range(new_width)]
        names = spec[key]
        index = names.index(old_names[0]) if old_names[0] in names else len(names)
        names[:] = [name for name in names if name not in old_names]
        names[index:index] = new_names
        layout = spec["designer"]["terminals"]
        for old in old_names: layout.pop(old, None)
        for bit, new in enumerate(new_names):
            layout[new] = {"side": self.term_side.currentText(),
                           "order": self.term_order.value() * 8 + bit,
                           "description": self.term_description.text()}
        return spec

    def refresh_terminals(self, select_id=None):
        select_id = select_id or (self.selected_terminal().id if self.selected_terminal() else None)
        self.terminal_list.blockSignals(True)
        self.terminal_list.clear()
        for terminal in sorted(self.model.terminals(), key=lambda c: (c.kind != "INPUT", c.params.get("_terminal", {}).get("order", 0))):
            item = QListWidgetItem(f"{'←' if terminal.kind == 'INPUT' else '→'}  {terminal.params.get('label', '?')}  ·  {bit_width(terminal)}b")
            item.setData(Qt.UserRole, terminal.id)
            self.terminal_list.addItem(item)
            if terminal.id == select_id: self.terminal_list.setCurrentItem(item)
        if not self.terminal_list.currentItem() and self.terminal_list.count():
            self.terminal_list.setCurrentRow(0)
        self.terminal_list.blockSignals(False)
        self.show_terminal()
        self.live_preview.update()
        self.terminal_preview.update()

    def show_terminal(self, *_):
        terminal = self.selected_terminal()
        if not terminal: return
        meta = terminal.params.get("_terminal", {})
        for widget in (self.term_name, self.term_width, self.term_side, self.term_order, self.term_description):
            widget.blockSignals(True)
        self.term_name.setText(terminal.params.get("label", ""))
        self.term_width.setValue(bit_width(terminal))
        self.term_side.setCurrentText(meta.get("side", "LEFT" if terminal.kind == "INPUT" else "RIGHT"))
        self.term_order.setValue(meta.get("order", 0))
        self.term_description.setText(meta.get("description", ""))
        for widget in (self.term_name, self.term_width, self.term_side, self.term_order, self.term_description):
            widget.blockSignals(False)
        self.terminal_preview.update()

    def add_terminal(self, direction):
        existing = {c.params.get("label") for c in self.model.terminals()}
        base = "IN" if direction == "INPUT" else "OUT"
        number = 1
        while base + str(number) in existing: number += 1
        self.push_history()
        terminal = self.model.add_terminal(base + str(number), direction)
        self.render(); self.refresh_terminals(terminal.id)
        self.set_status(f"Added {direction} terminal · connect it on the canvas")

    def remove_terminal(self):
        terminal = self.selected_terminal()
        if not terminal: return
        self.push_history()
        self.model.remove_terminal(terminal.id)
        self.render(); self.refresh_terminals()

    def apply_terminal(self):
        terminal = self.selected_terminal()
        if not terminal: return True
        before = self._snapshot()
        try:
            self.model.configure_terminal(terminal.id, name=self.term_name.text().strip(),
                                          width=self.term_width.value(), side=self.term_side.currentText(),
                                          order=self.term_order.value(), description=self.term_description.text())
            if self._snapshot() != before:
                self.push_history(before)
                self.render()
                self.refresh_terminals(terminal.id)
            return True
        except (ValueError, TypeError) as error:
            QMessageBox.warning(self, "Invalid terminal", str(error))
            return False

    def appearance_draft(self):
        return {"body_color": self.color_field.text().strip(), "width": self.width_field.value(),
                "height": self.height_field.value(), "label": self.label_field.text(),
                "short_description": self.short_field.text()}

    def load_appearance(self):
        self.name_field.setText(self.model.name)
        self.category_field.setCurrentText(self.model.category)
        self.description_field.setPlainText(self.model.description)
        self.color_field.setText(self.model.appearance["body_color"])
        self.width_field.setValue(self.model.appearance["width"])
        self.height_field.setValue(self.model.appearance["height"])
        self.label_field.setText(self.model.appearance["label"])
        self.short_field.setText(self.model.appearance["short_description"])
        self.live_preview.update()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color_field.text()), self, "Block body color")
        if color.isValid(): self.color_field.setText(color.name())

    def apply_appearance(self):
        before = self._snapshot()
        self.model.name = self.name_field.text().strip()
        self.model.category = self.category_field.currentText().strip()
        self.model.description = self.description_field.toPlainText()
        self.model.appearance.update(self.appearance_draft())
        try:
            # Appearance validation is independent of incomplete internal wiring.
            if (not self.model.name or not self.model.category or
                    not re.fullmatch(r"#[0-9a-fA-F]{6}", self.model.appearance["body_color"])):
                raise ValueError("Enter a name, category and six-digit body color, such as #29465a")
            if self._snapshot() != before:
                self.push_history(before)
                self._title()
                self.live_preview.update()
            return True
        except ValueError as error:
            self._restore(json.loads(before))
            QMessageBox.warning(self, "Invalid appearance", str(error))
            return False

    def _has_drafts(self):
        appearance = (self.name_field.text().strip() != self.model.name or
                      self.category_field.currentText().strip() != self.model.category or
                      self.description_field.toPlainText() != self.model.description or
                      self.appearance_draft() != self.model.appearance)
        terminal = self.selected_terminal()
        terminal_changed = False
        if terminal:
            meta = terminal.params.get("_terminal", {})
            terminal_changed = (self.term_name.text().strip() != terminal.params.get("label", "") or
                                self.term_width.value() != bit_width(terminal) or
                                self.term_side.currentText() != meta.get("side") or
                                self.term_order.value() != meta.get("order") or
                                self.term_description.text() != meta.get("description", ""))
        return appearance or terminal_changed

    def _snapshot(self, circuit_data=None):
        return json.dumps({"circuit": circuit_data or self.circuit.to_dict(), "appearance": self.model.appearance,
                           "name": self.model.name, "description": self.model.description,
                           "category": self.model.category})

    def push_history(self, snapshot=None):
        circuit_data = None
        if snapshot:
            parsed = json.loads(snapshot)
            if "circuit" in parsed:
                package = snapshot
            else:
                circuit_data = parsed
                package = self._snapshot(circuit_data)
        else:
            package = self._snapshot()
        self.history.append(package)
        if len(self.history) > 100: self.history.pop(0)
        self.future.clear()
        self.dirty = True
        self._title()

    def _restore(self, data):
        self.circuit = Circuit.from_dict(data["circuit"])
        self.sim = Simulator(self.circuit)
        self.model.circuit = self.circuit
        self.model.appearance = data["appearance"]
        self.model.name = data["name"]
        self.model.description = data["description"]
        self.model.category = data["category"]
        self.render(); self.refresh_terminals(); self.load_appearance(); self._title()

    def undo(self):
        if not self.history: return
        self.future.append(self._snapshot())
        self._restore(json.loads(self.history.pop()))
        self.dirty = True
        self._title()

    def redo(self):
        if not self.future: return
        self.history.append(self._snapshot())
        self._restore(json.loads(self.future.pop()))
        self.dirty = True
        self._title()

    def run_test_dialog(self):
        if not self.apply_terminal():
            return
        TestComponentDialog(self.model, self).exec()

    def show_preview(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("External Component Preview")
        dialog.resize(530, 360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(BlockPreview(self.model, self.appearance_draft,
                                      spec_provider=self.terminal_draft_spec))
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def save(self, force_new=False):
        try:
            if self._has_drafts() and not self.apply_terminal():
                return False
            if not self.apply_appearance():
                return False
            self.model.circuit = self.circuit
            definition = self.model.validate()
        except (ValueError, TypeError, KeyError) as error:
            QMessageBox.warning(self, "Cannot save component", str(error))
            return False
        dialog = SaveBlockDialog(self.global_library, self.model.name, parent=self)
        if self.model.library_id and not force_new:
            dialog.project.setChecked(False)
            dialog.global_library.setChecked(True)
        dialog.category.setCurrentText(self.model.category)
        dialog.description.setPlainText(self.model.description)
        if dialog.exec() != QDialog.Accepted: return False
        name = dialog.name.text().strip()
        try:
            # Validate again under the final name to catch recursive references.
            from component_library import validate_definition
            validate_definition(definition, name)
            if dialog.global_library.isChecked():
                if self.model.library_id and not force_new:
                    entry = self.global_library.update(self.model.library_id, name=name,
                                                       category=dialog.category.currentText(),
                                                       description=dialog.description.toPlainText(),
                                                       definition=definition)
                else:
                    entry = self.global_library.save(name, definition, dialog.category.currentText(),
                                                     dialog.description.toPlainText())
                self.model.library_id, self.model.version = entry["id"], entry["version"]
            elif force_new:
                self.model.library_id, self.model.version = None, 0
            if dialog.project.isChecked():
                project_name = name
                if project_name in self.parent_editor.circuit.blocks:
                    suffix = 2
                    while f"{name} {suffix}" in self.parent_editor.circuit.blocks: suffix += 1
                    project_name = f"{name} {suffix}"
                self.parent_editor.push_history()
                self.parent_editor.circuit.blocks[project_name] = deepcopy(definition)
            self.model.name = name
            self.model.category = dialog.category.currentText()
            self.model.description = dialog.description.toPlainText()
            self.load_appearance()
            self.parent_editor.populate_library()
            self.dirty = False
            self.history.clear(); self.future.clear()
            self._title()
            self.set_status(f"Saved {name}" + (f" · library v{self.model.version}" if dialog.global_library.isChecked() else ""))
            return True
        except (ValueError, TypeError, KeyError, OSError) as error:
            QMessageBox.warning(self, "Cannot save component", str(error))
            return False

    def save_as_component(self):
        return self.save(force_new=True)

    def export_definition(self):
        try:
            definition = self.model.validate()
            path, _ = QFileDialog.getSaveFileName(self, "Export component", self.model.name + ".json", "JSON (*.json)")
            if path:
                _atomic_json(Path(path if path.endswith(".json") else path + ".json"), definition)
        except (ValueError, TypeError, OSError) as error:
            QMessageBox.warning(self, "Cannot export", str(error))

    def closeEvent(self, event):
        if self.dirty or self._has_drafts():
            answer = QMessageBox.question(self, "Unsaved component", "Save changes to this component?",
                                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                          QMessageBox.Save)
            if answer == QMessageBox.Cancel or answer == QMessageBox.Save and not self.save():
                event.ignore(); return
        self.timer.stop()
        event.accept()
