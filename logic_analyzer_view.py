"""Docked logic analyzer using the Timing Diagram capture and time axis."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QComboBox, QSpinBox, QListWidget, QListWidgetItem,
                               QTextEdit, QTabWidget, QFileDialog, QMessageBox, QDialog, QCheckBox)

from logic_analyzer_model import LogicAnalyzer, format_value
from timing_view import WaveformView, SignalPicker


class LogicAnalyzerPanel(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.analysis = LogicAnalyzer(editor.timing_history)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.addWidget(QLabel("LOGIC ANALYZER · SIMULATION STEPS"))
        controls = QHBoxLayout()
        for title, callback in (("+ Channels", self.pick_channels), ("Remove", self.remove_channel),
                                ("Fit", self.view_fit)):
            button = QPushButton(title); button.clicked.connect(callback); controls.addWidget(button)
        root.addLayout(controls)
        options = QHBoxLayout()
        for title, factor in (("−", 0.8), ("+", 1.25)):
            button = QPushButton(title); button.clicked.connect(lambda _checked=False, factor=factor: self.view.zoom(factor))
            options.addWidget(button)
        self.radix = QComboBox(); self.radix.addItems(("binary", "hex", "decimal"))
        self.radix.currentTextChanged.connect(self.update_cursor)
        options.addWidget(self.radix)
        self.follow = QCheckBox("Follow")
        self.follow.setChecked(True)
        self.follow.toggled.connect(self.set_follow)
        options.addWidget(self.follow)
        root.addLayout(options)
        self.tabs = QTabWidget()
        wave_tab = QWidget(); wave_layout = QVBoxLayout(wave_tab)
        self.view = WaveformView(editor.timing_history)
        self.view.selectedChanged.connect(self.update_cursor)
        self.view.cursorChanged.connect(self.update_cursor)
        self.view.cursorChanged.connect(editor._analyzer_cursor_time_travel)
        self.view.followChanged.connect(self.follow.setChecked)
        wave_layout.addWidget(self.view)
        self.cursor = QLabel("Select captured signals to inspect")
        self.cursor.setWordWrap(True); wave_layout.addWidget(self.cursor)
        ranges = QHBoxLayout()
        self.start = QSpinBox(); self.end = QSpinBox()
        for spin in (self.start, self.end): spin.setRange(0, 1000000000)
        ranges.addWidget(QLabel("From step")); ranges.addWidget(self.start)
        ranges.addWidget(QLabel("To")); ranges.addWidget(self.end)
        all_button = QPushButton("All retained"); all_button.clicked.connect(self.reset_range)
        ranges.addWidget(all_button)
        wave_layout.addLayout(ranges)
        search_row = QHBoxLayout()
        self.search_kind = QComboBox(); self.search_kind.addItems(("change", "rising", "falling"))
        search_row.addWidget(self.search_kind)
        find_button = QPushButton("Find transitions"); find_button.clicked.connect(self.search)
        search_row.addWidget(find_button)
        measures = QPushButton("Pulse / period"); measures.clicked.connect(self.measure)
        search_row.addWidget(measures)
        export = QPushButton("Export CSV…"); export.clicked.connect(self.export)
        search_row.addWidget(export)
        wave_layout.addLayout(search_row)
        self.events = QListWidget(); self.events.setMaximumHeight(125)
        self.events.itemClicked.connect(self.jump_event)
        wave_layout.addWidget(self.events)
        self.tabs.addTab(wave_tab, "Waveforms")

        analysis_tab = QWidget(); analysis_layout = QVBoxLayout(analysis_tab)
        analysis_layout.addWidget(QLabel("Timing analysis uses recorded steps; it does not model physical delay."))
        analysis_layout.addWidget(QLabel("Waveform markers: amber = clock/source edge; teal = data/target change."))
        selection = QHBoxLayout()
        self.clock_signal = QComboBox(); self.data_signal = QComboBox()
        selection.addWidget(QLabel("Clock / source")); selection.addWidget(self.clock_signal)
        selection.addWidget(QLabel("Data / target")); selection.addWidget(self.data_signal)
        analysis_layout.addLayout(selection)
        cycles = QHBoxLayout()
        self.cycle_a = QSpinBox(); self.cycle_b = QSpinBox()
        for spin in (self.cycle_a, self.cycle_b): spin.setRange(0, 100000)
        cycles.addWidget(QLabel("Cycle A")); cycles.addWidget(self.cycle_a)
        cycles.addWidget(QLabel("Cycle B")); cycles.addWidget(self.cycle_b)
        analysis_layout.addLayout(cycles)
        for title, callback in (("Clock cycles", self.analyze_cycles),
                                ("Data around edge", self.analyze_spacing),
                                ("Observed transition offset", self.analyze_offset),
                                ("Compare cycles", self.compare_cycles)):
            button = QPushButton(title); button.clicked.connect(callback); analysis_layout.addWidget(button)
        self.report = QTextEdit(); self.report.setReadOnly(True)
        analysis_layout.addWidget(self.report, 1)
        self.tabs.addTab(analysis_tab, "Step analysis")
        root.addWidget(self.tabs, 1)
        self.reset_range()
        self.sync_tracks()

    def pick_channels(self):
        dialog = SignalPicker(self.editor.circuit, self)
        if dialog.exec() == QDialog.Accepted:
            added = 0
            for ref in dialog.selected_refs():
                added += self.editor.timing_history.add(ref, self.editor.sim)
            if added:
                self.editor.trace_history.record(self.editor.sim)
                self.editor.timing_panel.view.update_ranges()
            self.sync_tracks()

    def sync_tracks(self):
        prior_a, prior_b = self.clock_signal.currentData(), self.data_signal.currentData()
        for combo, prior in ((self.clock_signal, prior_a), (self.data_signal, prior_b)):
            combo.clear()
            for track in self.editor.timing_history.tracks.values():
                combo.addItem(track.label, track.ref)
            index = combo.findData(prior)
            if index >= 0: combo.setCurrentIndex(index)
        self.view.update_ranges(follow=self.view.follow_latest)
        self.update_cursor()

    def remove_channel(self):
        ref = self.view.selected_ref
        if ref is None: return
        self.editor.timing_history.remove(ref)
        self.view.selected_ref = None
        self.editor.timing_panel.view.update_ranges()
        self.sync_tracks()

    def set_follow(self, enabled):
        self.view.follow_latest = enabled
        if enabled: self.view.scroll_latest()

    def clear_analysis_markers(self):
        self.view.analysis_markers.clear()
        self.view.viewport().update()

    def reset_range(self):
        self.start.setValue(self.editor.timing_history.first_step)
        self.end.setValue(self.editor.timing_history.last_step)

    def on_step(self):
        if self.view.follow_latest:
            self.end.setValue(self.editor.timing_history.last_step)
        self.view.update_ranges(follow=True)
        self.update_cursor()

    def update_cursor(self):
        ref = self.view.selected_ref
        if ref not in self.editor.timing_history.tracks:
            self.cursor.setText("Select a waveform row; all distances are simulation steps")
            return
        step = self.view.cursor_step if self.view.cursor_step is not None else self.editor.timing_history.last_step
        value = self.editor.timing_history.value_at(ref, step)
        self.cursor.setText(f"Step {step} · {self.editor.timing_history.tracks[ref].label} = "
                            f"{format_value(value, self.radix.currentText())}")

    def view_fit(self):
        self.view.fit_all()
        self.update_cursor()

    def _selected(self):
        ref = self.view.selected_ref
        if ref is None:
            raise ValueError("Select a waveform row first")
        return ref

    def _range(self):
        return self.start.value(), self.end.value()

    def _error(self, error):
        QMessageBox.warning(self, "Logic Analyzer", str(error))

    def search(self):
        try:
            events = self.analysis.find(self._selected(), self.search_kind.currentText(), *self._range())
        except ValueError as error:
            self._error(error); return
        self.events.clear()
        for event in events:
            item = QListWidgetItem(f"Step {event.step} · {event.kind}: "
                                   f"{format_value(event.before, self.radix.currentText())} → "
                                   f"{format_value(event.after, self.radix.currentText())}")
            item.setData(Qt.UserRole, event.step)
            self.events.addItem(item)
        self.cursor.setText(f"{len(events)} recorded transition(s) in selected range")

    def jump_event(self, item):
        self.view.cursor_step = item.data(Qt.UserRole)
        self.view.follow_latest = False
        self.view.cursorChanged.emit()
        self.view.viewport().update()

    def measure(self):
        try:
            ref = self._selected()
            widths = self.analysis.pulse_widths(ref, *self._range())
            periods = self.analysis.clock_periods(ref, *self._range())
        except ValueError as error:
            self._error(error); return
        self.events.clear()
        for first, last, count in widths:
            self.events.addItem(f"HIGH pulse {first}→{last}: {count} steps")
        for first, last, count in periods:
            self.events.addItem(f"Rising-edge period {first}→{last}: {count} steps")
        if not widths and not periods: self.events.addItem("No complete pulse or period in the retained range")

    def _pair(self):
        first, second = self.clock_signal.currentData(), self.data_signal.currentData()
        if first is None or second is None:
            raise ValueError("Capture and select two channels first")
        return first, second

    def analyze_cycles(self):
        try:
            clock, _ = self._pair()
            rows = self.analysis.clock_cycles(clock, *self._range())
            self.report.setPlainText("\n".join(f"Cycle {i}: {row.start}→{row.end}, "
                                                f"HIGH {row.high_steps}, LOW {row.low_steps} steps"
                                                for i, row in enumerate(rows)) or "No complete recorded cycles")
        except ValueError as error: self._error(error)

    def analyze_spacing(self):
        try:
            clock, data = self._pair()
            rows = self.analysis.setup_hold_spacings(clock, data, *self._range())
            markers = []
            for row in rows:
                markers.append((row["edge"], "#e4b46f"))
                for field, direction in (("before_steps", -1), ("after_steps", 1)):
                    if row[field] is not None:
                        markers.append((row["edge"] + direction * row[field], "#65d7bd"))
            self.view.analysis_markers = list(dict.fromkeys(markers))[:300]
            self.view.viewport().update()
            self.report.setPlainText("\n".join(
                f"Edge {row['edge']}: data {format_value(row['data'])}; "
                f"previous change {row['before_steps']} steps before, next change "
                f"{row['after_steps']} steps after" + (" · SAME STEP: ordering unresolved" if row['same_step_change'] else "")
                for row in rows) or "No rising clock edges in range")
        except ValueError as error: self._error(error)

    def analyze_offset(self):
        try:
            source, target = self._pair()
            changes = self.analysis.transitions(source, *self._range())
            if not changes:
                self.report.setPlainText("No source transition in selected range"); return
            rows = []
            markers = []
            for event in changes[:100]:
                offset = self.analysis.observed_transition_offset(source, target, event.step)
                markers.append((event.step, "#e4b46f"))
                if offset is not None:
                    markers.append((event.step + offset, "#65d7bd"))
                rows.append(f"Source step {event.step} → next target change: "
                            f"{offset if offset is not None else 'not observed'} steps")
            self.view.analysis_markers = list(dict.fromkeys(markers))[:300]
            self.view.viewport().update()
            self.report.setPlainText("Observed offsets only; connectivity and causality are not implied.\n" + "\n".join(rows))
        except ValueError as error: self._error(error)

    def compare_cycles(self):
        try:
            clock, data = self._pair()
            rows = self.analysis.compare_cycles(clock, (data,), self.cycle_a.value(), self.cycle_b.value())
            self.report.setPlainText("\n".join(f"Offset {offset}: {format_value(a)} vs {format_value(b)}"
                                                for _, offset, a, b in rows) or "Selected cycles have identical captured values")
        except ValueError as error: self._error(error)

    def export(self):
        try:
            if not self.editor.timing_history.tracks:
                raise ValueError("Capture at least one signal first")
            path, _ = QFileDialog.getSaveFileName(self, "Export captured steps", "logicspace_capture.csv", "CSV (*.csv)")
            if not path: return
            count = self.analysis.export_csv(path, list(self.editor.timing_history.tracks),
                                             start=self.start.value(), end=self.end.value(),
                                             radix=self.radix.currentText())
            self.cursor.setText(f"Exported {count} simulation steps to {path}")
        except (ValueError, OSError) as error: self._error(error)
