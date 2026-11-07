"""Bounded, GUI-independent history of signals produced by the existing Simulator."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from engine import BusWire, bus_ports, pins

MISSING = object()
DEFAULT_LIMIT = 2000


@dataclass(frozen=True)
class SignalRef:
    kind: str  # "pin" or "wire"
    component_id: str = ""
    pin: str = ""
    direction: str = ""
    wire_id: str = ""

    @classmethod
    def component_pin(cls, component_id, pin, direction):
        if direction not in ("input", "output"):
            raise ValueError("Pin direction must be input or output")
        return cls("pin", component_id, pin, direction)

    @classmethod
    def wire(cls, wire_id):
        return cls("wire", wire_id=wire_id)

    @classmethod
    def bus_port(cls, component_id, port, direction):
        return cls("bus", component_id, port, direction)

    @classmethod
    def wire_bit(cls, wire_id, index):
        return cls("wire_bit", pin=str(index), wire_id=wire_id)

    def valid(self, circuit):
        if self.kind in ("wire", "wire_bit"):
            if self.kind == "wire_bit":
                wire = circuit.wires.get(self.wire_id)
                return isinstance(wire, BusWire) and self.pin.isdigit() and 0 <= int(self.pin) < wire.width
            return self.wire_id in circuit.wires
        component = circuit.components.get(self.component_id)
        if component is None:
            return False
        input_pins, output_pins = pins(component, circuit.blocks)
        if self.kind == "bus":
            return self.pin in bus_ports(component, circuit.blocks)[self.direction]
        return self.pin in (input_pins if self.direction == "input" else output_pins)

    def value(self, simulator):
        if self.kind in ("wire", "wire_bit"):
            wire = simulator.circuit.wires.get(self.wire_id)
            if wire is None: return None
            if isinstance(wire, BusWire):
                bits = tuple(simulator.outputs.get((wire.source, pin)) for pin in wire.source_bits)
                return bits[int(self.pin)] if self.kind == "wire_bit" else bits
            return simulator.outputs.get((wire.source, wire.source_pin))
        if self.kind == "bus":
            component = simulator.circuit.components[self.component_id]
            names = bus_ports(component, simulator.circuit.blocks)[self.direction][self.pin]
            if self.direction == "output":
                return tuple(simulator.outputs.get((self.component_id, pin)) for pin in names)
            values = simulator.inputs.get(self.component_id, {})
            return tuple(values.get(pin) for pin in names)
        if self.direction == "output":
            return simulator.outputs.get((self.component_id, self.pin))
        return simulator.inputs.get(self.component_id, {}).get(self.pin)

    def label(self, circuit):
        if self.kind in ("wire", "wire_bit"):
            wire = circuit.wires[self.wire_id]
            source = circuit.components[wire.source]
            target = circuit.components[wire.target]
            suffix = f"[{self.pin}]" if self.kind == "wire_bit" else (f" [{wire.width}b]" if isinstance(wire, BusWire) else "")
            return f"{source.params.get('label') or source.kind}.{wire.source_pin} → {target.params.get('label') or target.kind}.{wire.target_pin}{suffix}"
        component = circuit.components[self.component_id]
        name = component.params.get("label") or component.kind.removeprefix("BLOCK:")
        if self.kind == "bus":
            width = len(bus_ports(component, circuit.blocks)[self.direction][self.pin])
            return f"{name}.{self.pin}[{width - 1}:0]"
        return f"{name}.{self.pin}"


@dataclass
class SignalTrack:
    ref: SignalRef
    label: str
    color_index: int
    start_step: int
    events: deque = field(default_factory=deque)  # (step, 0|1|None), changes only


class TimingHistory:
    def __init__(self, limit=DEFAULT_LIMIT):
        self.limit = max(10, int(limit))
        self.tracks: dict[SignalRef, SignalTrack] = {}
        self.steps = deque()
        self._next_color = 0

    @property
    def first_step(self):
        return self.steps[0] if self.steps else 0

    @property
    def last_step(self):
        return self.steps[-1] if self.steps else 0

    def add(self, ref, simulator, label=None):
        if not ref.valid(simulator.circuit):
            raise ValueError("Signal no longer exists")
        if ref in self.tracks:
            return False
        step = simulator.circuit.tick
        track = SignalTrack(ref, label or ref.label(simulator.circuit), self._next_color, step)
        self._next_color += 1
        track.events.append((step, ref.value(simulator)))
        self.tracks[ref] = track
        if not self.steps:
            self.steps.append(step)
        return True

    def remove(self, ref):
        return self.tracks.pop(ref, None) is not None

    def clear_signals(self):
        self.tracks.clear()
        self.steps.clear()
        self._next_color = 0

    def remove_invalid(self, circuit):
        removed = [ref for ref in self.tracks if not ref.valid(circuit)]
        for ref in removed:
            self.remove(ref)
        return removed

    def set_limit(self, limit):
        self.limit = max(10, int(limit))
        self._trim()

    def record_step(self, simulator):
        if not self.tracks:
            return False
        step = simulator.circuit.tick
        if self.steps and step < self.steps[-1]:
            self.clear_history(simulator)
            return True
        if self.steps and step == self.steps[-1]:
            return False
        self.steps.append(step)
        for track in self.tracks.values():
            value = track.ref.value(simulator)
            if not track.events or track.events[-1][1] != value:
                track.events.append((step, value))
        self._trim()
        return True

    def clear_history(self, simulator):
        self.steps.clear()
        if not self.tracks:
            return
        step = simulator.circuit.tick
        self.steps.append(step)
        for track in self.tracks.values():
            track.start_step = step
            track.events.clear()
            track.events.append((step, track.ref.value(simulator)))

    def replace_from_frames(self, frames, circuit):
        """Rebuild selected waveforms after selecting a simulation branch."""
        frames = list(frames)[-self.limit:]
        self.steps = deque(frame.step for frame in frames)
        for track in self.tracks.values():
            track.events.clear()
            track.start_step = frames[0].step if frames else 0
            for frame in frames:
                value = frame.value(track.ref, circuit)
                if not track.events or track.events[-1][1] != value:
                    track.events.append((frame.step, value))

    def _trim(self):
        while len(self.steps) > self.limit:
            self.steps.popleft()
        if not self.steps:
            return
        oldest = self.steps[0]
        for track in self.tracks.values():
            while len(track.events) > 1 and track.events[1][0] <= oldest:
                track.events.popleft()
            if track.events and track.events[0][0] < oldest:
                track.events[0] = (oldest, track.events[0][1])
            track.start_step = max(track.start_step, oldest)

    def value_at(self, ref, step):
        track = self.tracks.get(ref)
        if track is None or step < track.start_step or not track.events:
            return MISSING
        events = track.events
        lo, hi = 0, len(events)
        while lo < hi:
            mid = (lo + hi) // 2
            if events[mid][0] <= step:
                lo = mid + 1
            else:
                hi = mid
        return events[lo - 1][1] if lo else MISSING
