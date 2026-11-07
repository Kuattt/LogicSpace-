"""Simulation-step breakpoints and watchpoints for the existing Simulator."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import uuid

from timing_model import SignalRef
from memory_model import memory_word
from engine import memory_geometry


@dataclass
class Breakpoint:
    id: str
    ref: SignalRef | None
    mode: str
    expected: object = None
    enabled: bool = True
    component_id: str | None = None
    address: int | None = None


@dataclass(frozen=True)
class BreakEvent:
    step: int
    breakpoint_id: str
    label: str
    before: object
    after: object
    reason: str


class BreakpointManager:
    MODES = ("equals", "not_equals", "rising", "falling", "change", "unknown", "watch", "conflict")

    def __init__(self, limit=2000):
        self.items: dict[str, Breakpoint] = {}
        self.last_values = {}
        self.events = deque(maxlen=max(10, int(limit)))
        self.last_conflicts = ()

    def add(self, ref, mode, simulator, expected=None):
        if mode not in self.MODES or mode == "conflict":
            raise ValueError("Invalid signal breakpoint mode")
        if not ref.valid(simulator.circuit):
            raise ValueError("Selected signal no longer exists")
        value = ref.value(simulator)
        if mode in ("rising", "falling") and isinstance(value, tuple):
            raise ValueError("Choose an individual bit for rising/falling edge")
        if mode in ("equals", "not_equals"):
            expected = self._expected(value, expected)
        item = Breakpoint(uuid.uuid4().hex, ref, mode, expected)
        self.items[item.id] = item
        self.last_values[item.id] = value
        return item

    def add_conflict(self, simulator):
        item = Breakpoint(uuid.uuid4().hex, None, "conflict")
        self.items[item.id] = item
        self.last_conflicts = tuple(simulator.errors + simulator.warnings)
        return item

    def add_memory_watch(self, component_id, address, simulator):
        component = simulator.circuit.components.get(component_id)
        if component is None or component.kind not in ("RAM", "ROM"):
            raise ValueError("Choose an existing RAM or ROM")
        _, _, depth = memory_geometry(component)
        if type(address) is not int or not 0 <= address < depth:
            raise ValueError(f"Memory address must be between 0 and {depth - 1}")
        item = Breakpoint(uuid.uuid4().hex, None, "memory_change",
                          component_id=component_id, address=address)
        self.items[item.id] = item
        self.last_values[item.id] = memory_word(component, address)
        return item

    @staticmethod
    def _expected(actual, expected):
        if isinstance(actual, tuple):
            width = len(actual)
            if expected is None:
                return tuple(None for _ in range(width))
            if type(expected) is int and 0 <= expected < (1 << width):
                return tuple((expected >> bit) & 1 for bit in range(width))
            if isinstance(expected, (tuple, list)) and len(expected) == width and all(
                    bit is None or type(bit) is int and bit in (0, 1) for bit in expected):
                return tuple(expected)
            raise ValueError(f"Expected value must fit in {width} bits")
        if expected is None or type(expected) is int and expected in (0, 1):
            return expected
        raise ValueError("Expected bit must be 0, 1 or X")

    def remove(self, identifier):
        self.items.pop(identifier, None)
        self.last_values.pop(identifier, None)

    def clear(self):
        self.items.clear()
        self.last_values.clear()
        self.events.clear()
        self.last_conflicts = ()

    def arm(self, simulator, *, clear_events=False):
        for item in self.items.values():
            if item.ref is not None and item.ref.valid(simulator.circuit):
                self.last_values[item.id] = item.ref.value(simulator)
            elif item.mode == "memory_change" and item.component_id in simulator.circuit.components:
                self.last_values[item.id] = memory_word(simulator.circuit.components[item.component_id], item.address)
        self.last_conflicts = tuple(simulator.errors + simulator.warnings)
        if clear_events: self.events.clear()

    def remove_invalid(self, circuit):
        removed = [identifier for identifier, item in self.items.items()
                   if (item.ref is not None and not item.ref.valid(circuit)) or
                   (item.mode == "memory_change" and
                    (item.component_id not in circuit.components or
                     circuit.components[item.component_id].kind not in ("RAM", "ROM") or
                     item.address >= memory_geometry(circuit.components[item.component_id])[2]))]
        for identifier in removed: self.remove(identifier)
        return removed

    def check(self, simulator):
        step = simulator.circuit.tick
        found = []
        for item in self.items.values():
            if not item.enabled:
                continue
            if item.mode == "conflict":
                conflicts = tuple(simulator.errors + simulator.warnings)
                if conflicts and conflicts != self.last_conflicts:
                    found.append(BreakEvent(step, item.id, "Circuit conflict", self.last_conflicts,
                                            conflicts, "; ".join(conflicts)))
                self.last_conflicts = conflicts
                continue
            if item.mode == "memory_change":
                component = simulator.circuit.components.get(item.component_id)
                if component is None or component.kind not in ("RAM", "ROM"): continue
                after = memory_word(component, item.address)
                before = self.last_values.get(item.id, after)
                self.last_values[item.id] = after
                if before != after:
                    found.append(BreakEvent(step, item.id,
                                            f"{component.kind} {component.id[:8]}[{item.address:#x}]",
                                            before, after, "memory change"))
                continue
            if not item.ref.valid(simulator.circuit):
                continue
            after = item.ref.value(simulator)
            before = self.last_values.get(item.id, after)
            self.last_values[item.id] = after
            matched = ((item.mode == "equals" and after == item.expected) or
                       (item.mode == "not_equals" and after != item.expected) or
                       (item.mode == "rising" and before == 0 and after == 1) or
                       (item.mode == "falling" and before == 1 and after == 0) or
                       (item.mode in ("change", "watch") and before != after) or
                       (item.mode == "unknown" and (after is None or isinstance(after, tuple) and None in after)))
            if matched:
                found.append(BreakEvent(step, item.id, item.ref.label(simulator.circuit), before, after, item.mode))
        self.events.extend(found)
        return found
