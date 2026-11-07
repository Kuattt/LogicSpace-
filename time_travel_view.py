"""Qt dock for simulation navigation, checkpoints, replay and state comparison."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                               QPushButton, QComboBox, QSpinBox, QListWidget, QListWidgetItem,
                               QTableWidget, QTableWidgetItem, QAbstractItemView, QInputDialog,
                               QMessageBox, QCheckBox)

from time_travel_model import DEFAULT_LIMIT, DEFAULT_MEMORY_MIB, topology_key


def value_text(value):
    if value is None:
        return "X"
    if isinstance(value, dict):
        return ", ".join(f"{key}: {value_text(bit)}" for key, bit in value.items()) or "{}"
    return str(value)


class TimeTravelPanel(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.history = editor.time_history
        self.external = None
        self._updating = False
        self._compare_initialized = False
        self.replay = QTimer(self)
        self.replay.setInterval(180)
        self.replay.timeout.connect(self._replay_next)
        self._build()
        self.refresh_panel()

    def _button(self, text, callback, layout, *, primary=False):
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(7)
        title = QLabel("TIME TRAVEL DEBUGGER")
        title.setObjectName("overline")
        root.addWidget(title)
        self.summary = QLabel("Step 0 / 0")
        self.summary.setObjectName("inspectName")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.availability = QLabel("")
        self.availability.setObjectName("hint")
        self.availability.setWordWrap(True)
        root.addWidget(self.availability)
        return_row = QHBoxLayout()
        self.return_button = self._button("Return to live history", self.return_to_live, return_row)
        self.return_button.hide()
        return_row.addStretch()
        root.addLayout(return_row)

        nav = QHBoxLayout()
        for text, callback in (("|◀", self.first), ("◀", self.back),
                               ("▶", self.forward), ("▶|", self.latest)):
            self._button(text, callback, nav)
        self.play_button = self._button("Play replay", self.toggle_replay, nav, primary=True)
        root.addLayout(nav)
        continuation = QHBoxLayout()
        self._button("Continue from this state", self.continue_here, continuation)
        continuation.addStretch()
        root.addLayout(continuation)
        branch_row = QHBoxLayout()
        branch_row.addWidget(QLabel("Branch"))
        self.branches = QComboBox()
        self.branches.currentIndexChanged.connect(self._branch_changed)
        branch_row.addWidget(self.branches, 1)
        self.step = QSpinBox()
        self.step.setRange(0, 1000000000)
        self.step.setFixedWidth(90)
        branch_row.addWidget(self.step)
        self._button("Jump", self.jump, branch_row)
        root.addLayout(branch_row)
        self.slider = QSpinBox()
        self.slider.setRange(0, 0)
        self.slider.setPrefix("Recorded position  ")
        self.slider.valueChanged.connect(self._position_changed)
        root.addWidget(self.slider)

        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel("States"))
        self.limit = QSpinBox()
        self.limit.setRange(1, 10000)
        self.limit.setValue(DEFAULT_LIMIT)
        self.limit.setSingleStep(100)
        self.limit.valueChanged.connect(self._limits_changed)
        limit_row.addWidget(self.limit)
        limit_row.addWidget(QLabel("Memory MiB"))
        self.memory = QSpinBox()
        self.memory.setRange(1, 1024)
        self.memory.setValue(DEFAULT_MEMORY_MIB)
        self.memory.valueChanged.connect(self._limits_changed)
        limit_row.addWidget(self.memory)
        root.addLayout(limit_row)

        root.addWidget(QLabel("CHECKPOINTS"))
        self.checkpoints = QListWidget()
        self.checkpoints.setFixedHeight(105)
        self.checkpoints.itemDoubleClicked.connect(lambda *_: self.jump_checkpoint())
        root.addWidget(self.checkpoints)
        checkpoints_row = QHBoxLayout()
        for text, callback in (("+ Save", self.add_checkpoint), ("Jump", self.jump_checkpoint),
                               ("Rename", self.rename_checkpoint), ("Delete", self.delete_checkpoint)):
            self._button(text, callback, checkpoints_row)
        root.addLayout(checkpoints_row)
        checkpoint_compare = QHBoxLayout()
        self._button("A ← checkpoint", lambda: self._checkpoint_compare_target("a"), checkpoint_compare)
        self._button("B ← checkpoint", lambda: self._checkpoint_compare_target("b"), checkpoint_compare)
        root.addLayout(checkpoint_compare)

        root.addWidget(QLabel("COMPARE STATES"))
        grid = QGridLayout()
        self.a_branch, self.b_branch = QComboBox(), QComboBox()
        self.a_step, self.b_step = QSpinBox(), QSpinBox()
        for spin in (self.a_step, self.b_step):
            spin.setRange(0, 1000000000)
        grid.addWidget(QLabel("A"), 0, 0); grid.addWidget(self.a_branch, 0, 1); grid.addWidget(self.a_step, 0, 2)
        grid.addWidget(QLabel("B"), 1, 0); grid.addWidget(self.b_branch, 1, 1); grid.addWidget(self.b_step, 1, 2)
        root.addLayout(grid)
        compare_row = QHBoxLayout()
        self._button("A ← current", lambda: self._set_compare_target("a"), compare_row)
        self._button("B ← current", lambda: self._set_compare_target("b"), compare_row)
        self._button("Compare", self.compare, compare_row, primary=True)
        root.addLayout(compare_row)
        self.show_unchanged = QCheckBox("Show unchanged values")
        root.addWidget(self.show_unchanged)
        self.differences = QTableWidget(0, 4)
        self.differences.setHorizontalHeaderLabels(("Type", "Signal or state", "A", "B"))
        self.differences.horizontalHeader().setStretchLastSection(True)
        self.differences.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.differences.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.differences.itemClicked.connect(self._select_difference)
        root.addWidget(self.differences, 1)
        self.difference_status = QLabel("Select two retained states to compare")
        self.difference_status.setObjectName("hint")
        self.difference_status.setWordWrap(True)
        root.addWidget(self.difference_status)
        self._shown_differences = []

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_panel()

    def reset_for_circuit(self):
        self.pause_replay()
        self.external = None
        self._compare_initialized = False
        self.a_step.setValue(0)
        self.b_step.setValue(0)
        self.differences.setRowCount(0)
        self._shown_differences = []
        self.difference_status.setText("Select two retained states to compare")
        self.refresh_panel()

    def refresh_panel(self):
        if self._updating:
            return
        self._updating = True
        history = self.history
        self.return_button.setVisible(self.external is not None)
        current = history.current
        branch = history.branch
        ids = [self.branches.itemData(i) for i in range(self.branches.count())]
        if ids != list(history.branches):
            self.branches.clear(); self.a_branch.clear(); self.b_branch.clear()
            for item in history.branches.values():
                for combo in (self.branches, self.a_branch, self.b_branch):
                    combo.addItem(item.name, item.id)
        index = self.branches.findData(history.active_branch)
        self.branches.setCurrentIndex(index)
        steps = history.available_steps()
        self.slider.setRange(0, max(0, len(steps) - 1))
        if current:
            self.step.setValue(current.step)
            if current.step in steps:
                self.slider.setValue(steps.index(current.step))
        first = steps[0] if steps else "—"
        latest = branch.latest_step if branch.latest_step is not None else "—"
        if self.external is None:
            self.summary.setText(f"Step {current.step if current else '—'} / {latest}  ·  {branch.name}" +
                                 ("  ·  HISTORICAL" if history.is_historical else ""))
        self.availability.setText(f"Available {first}–{latest} · {len(steps)} states in branch · "
                                  f"{len(history.snapshots)} total · {history.total_bytes / 1048576:.1f} MiB" +
                                  (" · one state exceeds memory cap" if history.total_bytes > history.memory_limit else ""))
        self.limit.setValue(history.limit)
        self.memory.setValue(history.memory_limit // 1048576)
        self._refresh_checkpoints()
        for combo in (self.a_branch, self.b_branch):
            if combo.currentIndex() < 0:
                combo.setCurrentIndex(combo.findData(history.active_branch))
        if not self._compare_initialized and current:
            self.a_step.setValue(steps[-2] if len(steps) > 1 else current.step)
            self.b_step.setValue(current.step)
            self._compare_initialized = True
        self._updating = False

    def _refresh_checkpoints(self):
        selected = self.checkpoints.currentItem().data(Qt.UserRole) if self.checkpoints.currentItem() else None
        self.checkpoints.clear()
        for checkpoint in self.history.checkpoints.values():
            branch = self.history.branches.get(checkpoint.branch_id)
            available = self.history.checkpoint_available(checkpoint)
            item = QListWidgetItem(f"{checkpoint.name} · {branch.name if branch else checkpoint.branch_id} "
                                   f"· step {checkpoint.step}" + ("  [expired]" if not available else ""))
            item.setData(Qt.UserRole, checkpoint.id)
            if not available:
                item.setForeground(QColor("#e7aa60"))
            self.checkpoints.addItem(item)
            if checkpoint.id == selected:
                self.checkpoints.setCurrentItem(item)

    def _navigate(self, step, branch_id=None, *, replay=False):
        if not replay:
            self.pause_replay()
        self.external = None
        try:
            self.editor.navigate_time(step, branch_id)
        except ValueError as error:
            self.difference_status.setText(str(error))

    def _branch_changed(self, *_):
        if self._updating:
            return
        branch_id = self.branches.currentData()
        branch = self.history.branches.get(branch_id)
        if branch and branch.latest_step is not None:
            self._navigate(branch.latest_step, branch_id)
        elif branch:
            self.difference_status.setText("This branch has no retained simulation states")
            self._updating = True
            self.branches.setCurrentIndex(self.branches.findData(self.history.active_branch))
            self._updating = False

    def _position_changed(self, position):
        if self._updating:
            return
        steps = self.history.available_steps()
        if 0 <= position < len(steps):
            self._navigate(steps[position])

    def first(self):
        steps = self.history.available_steps()
        if steps: self._navigate(steps[0])

    def back(self):
        steps = self.history.available_steps()
        current = self.history.current
        if current and current.step in steps:
            position = steps.index(current.step)
            if position: self._navigate(steps[position - 1])

    def forward(self):
        steps = self.history.available_steps()
        current = self.history.current
        if current and current.step in steps:
            position = steps.index(current.step)
            if position + 1 < len(steps): self._navigate(steps[position + 1])

    def latest(self):
        step = self.history.latest_step
        if step is not None: self._navigate(step)

    def continue_here(self):
        self.pause_replay()
        if self.external is not None:
            self.difference_status.setText("Testbench inspection is isolated; return to live history to create a branch")
            return
        if not self.history.is_historical:
            self.difference_status.setText("This is already the latest state of the selected branch")
            return
        self.history.fork()
        self.editor._sync_time_branch()
        self.refresh_panel()
        self.editor.set_status(f"Continuing from step {self.history.current.step} on {self.history.branch.name}")

    def jump(self):
        self._navigate(self.step.value())

    def toggle_replay(self):
        if self.external is not None:
            self.difference_status.setText("Testbench inspection is isolated; return to live history to replay")
            return
        if self.replay.isActive():
            self.pause_replay()
        else:
            self.editor.timer.stop()
            self.editor.run_button.setText("▶ Run")
            self.play_button.setText("Pause replay")
            self.replay.start()

    def pause_replay(self):
        self.replay.stop()
        self.play_button.setText("Play replay")

    def return_to_live(self):
        self.external = None
        self.refresh_panel()
        self.difference_status.setText("Showing live circuit history")

    def _replay_next(self):
        current = self.history.current
        steps = self.history.available_steps()
        if not current or current.step not in steps or current.step == steps[-1]:
            self.pause_replay(); return
        self._navigate(steps[steps.index(current.step) + 1], replay=True)

    def _limits_changed(self, *_):
        if self._updating:
            return
        if self.external is not None:
            self.return_to_live()
        self.history.set_limits(limit=self.limit.value(), memory_mib=self.memory.value())
        if self.history.current is not None and self.history.current.id in self.history.branch.states.values():
            self.editor.navigate_time(self.history.current.step, self.history.active_branch)
        self.refresh_panel()

    def _selected_checkpoint(self):
        item = self.checkpoints.currentItem()
        return self.history.checkpoints.get(item.data(Qt.UserRole)) if item else None

    def add_checkpoint(self):
        name, ok = QInputDialog.getText(self, "Save checkpoint", "Name", text=f"Step {self.history.current.step}")
        if not ok: return
        try:
            self.history.add_checkpoint(name)
            self.refresh_panel()
        except ValueError as error:
            QMessageBox.warning(self, "Checkpoint", str(error))

    def jump_checkpoint(self):
        checkpoint = self._selected_checkpoint()
        if checkpoint:
            self._navigate(checkpoint.step, checkpoint.branch_id)

    def rename_checkpoint(self):
        checkpoint = self._selected_checkpoint()
        if not checkpoint: return
        name, ok = QInputDialog.getText(self, "Rename checkpoint", "Name", text=checkpoint.name)
        if not ok: return
        try:
            self.history.rename_checkpoint(checkpoint.id, name)
            self.refresh_panel()
        except ValueError as error:
            QMessageBox.warning(self, "Checkpoint", str(error))

    def delete_checkpoint(self):
        checkpoint = self._selected_checkpoint()
        if checkpoint:
            self.history.delete_checkpoint(checkpoint.id)
            self.refresh_panel()

    def _set_compare_target(self, which):
        combo, spin = (self.a_branch, self.a_step) if which == "a" else (self.b_branch, self.b_step)
        combo.setCurrentIndex(combo.findData(self.history.active_branch))
        if self.history.current:
            spin.setValue(self.history.current.step)

    def _checkpoint_compare_target(self, which):
        checkpoint = self._selected_checkpoint()
        if not checkpoint or not self.history.checkpoint_available(checkpoint):
            self.difference_status.setText("Select an available checkpoint")
            return
        combo, spin = (self.a_branch, self.a_step) if which == "a" else (self.b_branch, self.b_step)
        combo.setCurrentIndex(combo.findData(checkpoint.branch_id))
        spin.setValue(checkpoint.step)

    def _display_differences(self, differences, heading):
        self._shown_differences = differences[:2000]
        self.differences.setRowCount(len(self._shown_differences))
        for row, difference in enumerate(self._shown_differences):
            for column, value in enumerate((difference.category, difference.label,
                                            value_text(difference.before), value_text(difference.after))):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if difference.changed:
                    item.setForeground(QColor("#f6c779" if column > 1 else "#e7edf7"))
                else:
                    item.setForeground(QColor("#8292a9"))
                self.differences.setItem(row, column, item)
        self.differences.setColumnWidth(0, 54)
        self.differences.setColumnWidth(1, 145)
        self.differences.setColumnWidth(2, 58)
        suffix = f" · showing first {len(self._shown_differences)}" if len(differences) > 2000 else ""
        self.difference_status.setText(f"{heading} · {sum(item.changed for item in differences)} changed, "
                                       f"{len(differences)} rows{suffix}")

    def compare(self):
        self.external = None
        self.refresh_panel()
        first = self.history.snapshot_at(self.a_branch.currentData(), self.a_step.value())
        second = self.history.snapshot_at(self.b_branch.currentData(), self.b_step.value())
        try:
            differences = self.history.compare(self.editor.circuit, first, second,
                                               include_unchanged=self.show_unchanged.isChecked())
            self._display_differences(differences, f"Step {first.step} → {second.step}")
        except ValueError as error:
            self.difference_status.setText(str(error))

    def _select_difference(self, item):
        row = item.row()
        if not 0 <= row < len(self._shown_differences):
            return
        difference = self._shown_differences[row]
        if self.external and self.external[0].topology != topology_key(self.editor.circuit):
            self.difference_status.setText("The testbench circuit differs from the live canvas; highlight is unavailable")
            return
        ref = difference.signal_ref
        if ref and ref.valid(self.editor.circuit):
            self.editor.focus_trace_ref(ref)
            if ref.kind == "wire":
                self.editor.set_trace_highlight((), (ref.wire_id,), (), (ref.wire_id,))
            else:
                self.editor.set_trace_highlight((ref.component_id,), (), (ref.component_id,), ())
        elif difference.component_id in self.editor.component_items:
            cid = difference.component_id
            self.editor.scene.clearSelection()
            item = self.editor.component_items[cid]
            item.setSelected(True)
            self.editor.canvas.centerOn(item)
            self.editor.set_trace_highlight((cid,), (), (cid,), ())

    def inspect_testbench(self, result, step, mode="open"):
        """Show isolated test facts without changing the editor simulator."""
        current = result.time_snapshots.get(step)
        if current is None:
            self.difference_status.setText("The failed step snapshot was not retained")
            return
        self.pause_replay()
        self.external = (current, result, step)
        self.return_button.show()
        self.summary.setText(f"TESTBENCH {result.name} · step {step} · isolated inspection")
        self.availability.setText("The live circuit and its simulation state are unchanged.")
        if mode == "expected":
            from time_travel_model import StateDifference
            expected = result.expected_by_step.get(step, {})
            rows = [StateDifference("Expected", result.signal_labels.get(sid, sid), value,
                                    result.observations[step].get(sid),
                                    result.signal_refs[sid].component_id or None, result.signal_refs[sid])
                    for sid, value in expected.items()]
            if not rows:
                self.differences.setRowCount(0)
                self._shown_differences = []
                self.difference_status.setText("No expected equals values were recorded at this step")
                return
            self._display_differences(rows, "Expected → actual")
        else:
            other = result.previous_time_snapshots.get(step) if mode == "previous" else current
            if other is None:
                self.differences.setRowCount(0)
                self._shown_differences = []
                self.difference_status.setText("Previous step snapshot is unavailable")
                return
            circuit = result.snapshots[step].circuit
            rows = self.history.compare(circuit, other, current, include_unchanged=mode == "open" or
                                        self.show_unchanged.isChecked())
            self._display_differences(rows, "Previous → failed step" if mode == "previous" else
                                      "Recorded state at failed step")
