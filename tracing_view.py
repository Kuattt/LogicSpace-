"""Signal tracing dock for the existing LogicSpace editor."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QCheckBox, QTabWidget, QTreeWidget, QTreeWidgetItem,
                               QTextEdit, QDialog)

from timing_view import SignalPicker
from tracing_model import TraceAnalyzer, TraceFrame, value_text


class SignalTracingPanel(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.ref = None
        self.reports = []
        self.highlight_enabled = True
        self.external = None
        self.can_highlight = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        heading = QLabel("SIGNAL TRACING")
        heading.setObjectName("overline")
        layout.addWidget(heading)
        self.summary = QLabel("Select a pin or wire to trace")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("inspectName")
        layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        choose = QPushButton("Choose signal")
        choose.clicked.connect(self.choose_signal)
        clear = QPushButton("Clear highlight")
        clear.clicked.connect(self.clear_highlight)
        buttons.addWidget(choose)
        buttons.addWidget(clear)
        layout.addLayout(buttons)
        self.cursor = QCheckBox("Use Timing Diagram cursor")
        self.cursor.toggled.connect(self.refresh)
        layout.addWidget(self.cursor)
        self.tabs = QTabWidget()
        self.backward_tree = self._tree()
        self.forward_tree = self._tree()
        self.explain_text = QTextEdit()
        self.explain_text.setReadOnly(True)
        self.tabs.addTab(self.backward_tree, "Backward")
        self.tabs.addTab(self.forward_tree, "Forward")
        self.tabs.addTab(self.explain_text, "Explain")
        self.tabs.currentChanged.connect(self.update_highlight)
        layout.addWidget(self.tabs, 1)
        self.note = QLabel("Blue: connected path · amber: locally influencing path.\n"
                           "Connections alone do not prove causation.")
        self.note.setWordWrap(True)
        self.note.setObjectName("hint")
        layout.addWidget(self.note)

    def _tree(self):
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.itemClicked.connect(self._item_clicked)
        return tree

    def choose_signal(self):
        dialog = SignalPicker(self.editor.circuit, self)
        dialog.setWindowTitle("Choose signal to trace")
        if dialog.exec() == QDialog.Accepted and dialog.selected_refs():
            self.select_signal(dialog.selected_refs()[0])

    def select_signal(self, ref, tab=0):
        self.ref = ref
        self.external = None
        self.cursor.setEnabled(True)
        self.highlight_enabled = True
        self.tabs.setCurrentIndex(tab)
        self.refresh()

    def select_snapshot(self, ref, circuit, frame, simulator, label="Testbench failure", expectation=""):
        """Inspect an immutable testbench failure without touching the live editor."""
        self.ref = ref
        self.external = (circuit, frame, simulator, label, expectation)
        self.cursor.setChecked(False)
        self.cursor.setEnabled(False)
        self.highlight_enabled = True
        self.tabs.setCurrentIndex(2)
        self.refresh()

    def on_timing_cursor(self):
        if self.external is not None:
            return
        view = self.editor.timing_panel.view
        if view.cursor_step is not None and not view.follow_latest:
            self.cursor.setChecked(True)
        if self.isVisible() and not self.editor._trace_refresh_suppressed:
            self.refresh()

    def _observation(self):
        if self.external is not None:
            return self.external[1], False, ""
        history = getattr(self.editor, "time_history", None)
        if history is not None and history.is_historical:
            snapshot = history.current
            if snapshot is None:
                return None, True, "Selected simulation state has expired."
            return snapshot.frame, True, ""
        view = self.editor.timing_panel.view
        if self.cursor.isChecked():
            step = view.cursor_step
            if step is None:
                return None, True, "Move the Timing Diagram cursor to a recorded step."
            frame = self.editor.trace_history.at(step)
            if frame is None:
                return None, True, f"Step {step} is outside retained causal history or was not captured."
            return frame, True, ""
        return TraceFrame.from_simulator(self.editor.sim), False, ""

    def refresh(self, *_):
        self.backward_tree.clear()
        self.forward_tree.clear()
        self.explain_text.clear()
        self.reports = []
        if self.ref is None:
            self.summary.setText("Select a pin or wire to trace")
            self.editor.clear_trace_highlight()
            return
        circuit = self.external[0] if self.external else self.editor.circuit
        simulator = self.external[2] if self.external else self.editor.sim
        self.can_highlight = self._same_topology(circuit, self.editor.circuit)
        if not self.ref.valid(circuit):
            self.summary.setText("Signal was deleted or its pin changed")
            self.explain_text.setPlainText("Choose another pin or wire.")
            self.editor.clear_trace_highlight()
            return
        invalid = circuit.validate()
        if invalid:
            self.summary.setText("Circuit wiring is invalid")
            self.explain_text.setPlainText("Fix these connections before tracing:\n" + "\n".join(invalid))
            self.editor.clear_trace_highlight()
            return
        frame, historical, issue = self._observation()
        historical = historical or self.external is not None
        if issue:
            self.summary.setText(issue)
            self.explain_text.setPlainText(issue + " Current values were not substituted.")
            self.editor.clear_trace_highlight()
            return
        label = self.ref.label(circuit)
        value = frame.value(self.ref, circuit)
        context = self.external[3] if self.external else ("Captured" if historical else "Live")
        self.summary.setText(f"{label} = {value_text(value)}\n"
                             f"{context} simulation step {frame.step}")
        backward = TraceAnalyzer(circuit, frame, simulator, historical=historical)
        forward = TraceAnalyzer(circuit, frame, simulator, historical=historical)
        self._add_node(self.backward_tree, None, backward.backward(self.ref))
        self._add_node(self.forward_tree, None, forward.forward(self.ref))
        self.backward_tree.expandToDepth(2)
        self.forward_tree.expandToDepth(2)
        explanation = TraceAnalyzer(circuit, frame, simulator,
                                    historical=historical).explain(self.ref)
        if self.external and self.external[4]:
            explanation.insert(0, self.external[4] + "\nThe trace below explains the observed value; it does not prove why the expectation was chosen.")
        self.explain_text.setPlainText("\n\n".join(explanation))
        self.reports = [backward, forward]
        self.update_highlight()

    @staticmethod
    def _same_topology(left, right):
        if set(left.components) != set(right.components) or set(left.wires) != set(right.wires):
            return False
        if any(left.components[cid].kind != right.components[cid].kind for cid in left.components):
            return False
        return all((type(w), w.source, w.source_pin, w.target, w.target_pin,
                    getattr(w, "width", 1), tuple(getattr(w, "source_bits", ())), tuple(getattr(w, "target_bits", ()))) ==
                   (type(right.wires[wid]), right.wires[wid].source, right.wires[wid].source_pin,
                    right.wires[wid].target, right.wires[wid].target_pin,
                    getattr(right.wires[wid], "width", 1), tuple(getattr(right.wires[wid], "source_bits", ())),
                    tuple(getattr(right.wires[wid], "target_bits", ())))
                   for wid, w in left.wires.items())

    def _add_node(self, tree, parent, node):
        item = QTreeWidgetItem([node.text])
        item.setData(0, Qt.UserRole, node.ref)
        if node.active:
            item.setForeground(0, QColor("#f6c779"))
        if parent is None:
            tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        for child in node.children:
            self._add_node(tree, item, child)

    def _item_clicked(self, item, _column):
        ref = item.data(0, Qt.UserRole)
        if ref is not None:
            self.editor.focus_trace_ref(ref)

    def update_highlight(self, *_):
        if not self.reports or not self.highlight_enabled:
            return
        if not self.can_highlight:
            self.editor.clear_trace_highlight()
            return
        report = self.reports[1] if self.tabs.currentIndex() == 1 else self.reports[0]
        self.editor.set_trace_highlight(report.connected_components, report.connected_wires,
                                        report.active_components, report.active_wires)

    def clear_highlight(self):
        self.highlight_enabled = False
        self.editor.clear_trace_highlight()
