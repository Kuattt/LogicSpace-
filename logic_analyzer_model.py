"""Step-based analysis of the existing TimingHistory; no second simulator."""
from __future__ import annotations

import csv
from dataclasses import dataclass

from timing_model import MISSING, TimingHistory


def format_value(value, radix="binary"):
    if value is MISSING:
        return "—"
    if value is None:
        return "X"
    if isinstance(value, (tuple, list)):
        binary = "".join("X" if bit is None else str(bit) for bit in reversed(value))
        if radix == "binary":
            return binary
        if None in value:
            return "X (" + binary + ")"
        integer = sum(bit << index for index, bit in enumerate(value))
    else:
        integer = value
    if radix == "hex":
        digits = (len(value) + 3) // 4 if isinstance(value, (tuple, list)) else 1
        return f"0x{integer:0{digits}X}"
    if radix == "decimal":
        return str(integer)
    return str(integer)


@dataclass(frozen=True)
class Transition:
    step: int
    before: object
    after: object
    kind: str


@dataclass(frozen=True)
class Cycle:
    start: int
    end: int
    high_steps: int
    low_steps: int


class LogicAnalyzer:
    """Queries captured values only. All distances are simulation steps."""
    def __init__(self, history: TimingHistory):
        self.history = history

    def _track(self, ref):
        if ref not in self.history.tracks:
            raise ValueError("Capture this signal in Logic Analyzer or Timing Diagram first")
        return self.history.tracks[ref]

    def _range(self, start=None, end=None):
        first = self.history.first_step if start is None else int(start)
        last = self.history.last_step if end is None else int(end)
        if first > last or first < self.history.first_step or last > self.history.last_step:
            raise ValueError("Selected range is outside retained simulation history")
        return first, last

    def transitions(self, ref, start=None, end=None):
        first, last = self._range(start, end)
        events = list(self._track(ref).events)
        result = []
        for (prior_step, before), (step, after) in zip(events, events[1:]):
            if not first <= step <= last:
                continue
            kind = "rising" if before == 0 and after == 1 else (
                "falling" if before == 1 and after == 0 else "change")
            result.append(Transition(step, before, after, kind))
        return result

    def find(self, ref, kind="change", start=None, end=None):
        if kind not in ("rising", "falling", "change"):
            raise ValueError("Search for rising, falling or change")
        events = self.transitions(ref, start, end)
        return [event for event in events if kind == "change" or event.kind == kind]

    def pulse_widths(self, ref, start=None, end=None):
        rises = None
        widths = []
        for event in self.transitions(ref, start, end):
            if event.kind == "rising":
                rises = event.step
            elif event.kind == "falling" and rises is not None:
                widths.append((rises, event.step, event.step - rises))
                rises = None
        return widths

    def clock_periods(self, ref, start=None, end=None):
        rises = [event.step for event in self.find(ref, "rising", start, end)]
        return [(a, b, b - a) for a, b in zip(rises, rises[1:])]

    def clock_cycles(self, ref, start=None, end=None):
        self._track(ref)
        cycles = []
        for first, last, _ in self.clock_periods(ref, start, end):
            values = [self.history.value_at(ref, step) for step in range(first, last)]
            if any(value not in (0, 1) for value in values):
                continue
            high = values.count(1)
            cycles.append(Cycle(first, last, high, len(values) - high))
        return cycles

    def observed_transition_offset(self, source, target, source_step, max_steps=100):
        """Observed step offset, never a physical or proven causal delay."""
        self._track(source); self._track(target)
        if source_step not in {event.step for event in self.transitions(source)}:
            raise ValueError("Source did not change at that recorded step")
        end = min(self.history.last_step, source_step + max_steps)
        target_events = self.transitions(target, source_step, end)
        return None if not target_events else target_events[0].step - source_step

    def setup_hold_spacings(self, clock, data, start=None, end=None):
        """Nearest recorded data transitions around rising edges, in steps only."""
        self._track(data)
        changes = [event.step for event in self.transitions(data)]
        result = []
        for edge in self.find(clock, "rising", start, end):
            before = max((step for step in changes if step < edge.step), default=None)
            after = min((step for step in changes if step >= edge.step), default=None)
            result.append({"edge": edge.step, "data": self.history.value_at(data, edge.step),
                           "before_steps": None if before is None else edge.step - before,
                           "after_steps": None if after is None else after - edge.step,
                           "same_step_change": after == edge.step})
        return result

    def compare_cycles(self, clock, refs, first_index, second_index):
        cycles = self.clock_cycles(clock)
        if min(first_index, second_index) < 0 or max(first_index, second_index) >= len(cycles):
            raise ValueError("Cycle index is outside retained history")
        first, second = cycles[first_index], cycles[second_index]
        rows = []
        for ref in refs:
            self._track(ref)
            length = min(first.end - first.start, second.end - second.start)
            for offset in range(length):
                a = self.history.value_at(ref, first.start + offset)
                b = self.history.value_at(ref, second.start + offset)
                if a != b:
                    rows.append((ref, offset, a, b))
        return rows

    def export_csv(self, path, refs, *, start=None, end=None, radix="binary"):
        first, last = self._range(start, end)
        if radix not in ("binary", "hex", "decimal"):
            raise ValueError("Choose binary, hex or decimal display")
        tracks = [self._track(ref) for ref in refs]
        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["simulation_step"] + [track.label for track in tracks])
            for step in range(first, last + 1):
                writer.writerow([step] + [format_value(self.history.value_at(track.ref, step), radix)
                                          for track in tracks])
        return last - first + 1
