"""GUI-independent connectivity and simulation-backed signal explanations.

Connectivity is topology. Causal influence here means local counterfactual
sensitivity at the captured input values; sequential causes use the actual
sampled inputs and state transition recorded by Simulator.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field

from engine import Circuit, Simulator, SEQUENTIAL, LOGIC_GATES, ANALOG, BusWire, bus_ports, wire_bit_pairs, pins
from timing_model import SignalRef

_NO_SAMPLE = object()


def value_text(value):
    if isinstance(value, (tuple, list)):
        binary = "".join("X" if bit is None else str(bit) for bit in reversed(value))
        number = None if None in value else sum(bit << index for index, bit in enumerate(value))
        return f"{binary} (0x{number:X})" if number is not None else binary
    return "X" if value is None else str(value)


@dataclass
class TraceFrame:
    step: int
    inputs: dict
    outputs: dict
    transitions: dict = field(default_factory=dict)
    forced_inputs: dict = field(default_factory=dict)
    forced_outputs: dict = field(default_factory=dict)
    block_events: dict = field(default_factory=dict)

    @classmethod
    def from_simulator(cls, simulator, *, include_block_events=True):
        return cls(simulator.circuit.tick,
                   {cid: dict(values) for cid, values in simulator.inputs.items()},
                   dict(simulator.outputs), deepcopy(simulator.last_transitions),
                   dict(simulator.forced_inputs), dict(simulator.forced_outputs),
                   deepcopy(simulator.last_block_events) if include_block_events else {})

    def value(self, ref, circuit):
        if ref.kind in ("wire", "wire_bit"):
            wire = circuit.wires.get(ref.wire_id)
            if wire is None: return None
            if isinstance(wire, BusWire):
                values = tuple(self.outputs.get((wire.source, pin)) for pin in wire.source_bits)
                return values[int(ref.pin)] if ref.kind == "wire_bit" else values
            return self.outputs.get((wire.source, wire.source_pin))
        if ref.kind == "bus":
            component = circuit.components[ref.component_id]
            names = bus_ports(component, circuit.blocks)[ref.direction][ref.pin]
            if ref.direction == "output":
                return tuple(self.outputs.get((ref.component_id, name)) for name in names)
            values = self.inputs.get(ref.component_id, {})
            return tuple(values.get(name) for name in names)
        if ref.direction == "input":
            return self.inputs.get(ref.component_id, {}).get(ref.pin)
        return self.outputs.get((ref.component_id, ref.pin))


class TraceHistory:
    """Bounded full signal facts for steps that the Timing Diagram captures."""
    def __init__(self, limit=2000):
        self.limit = max(10, int(limit))
        self.frames = deque()

    def clear(self):
        self.frames.clear()

    def set_limit(self, limit):
        self.limit = max(10, int(limit))
        while len(self.frames) > self.limit:
            self.frames.popleft()

    def record(self, simulator):
        frame = TraceFrame.from_simulator(simulator, include_block_events=False)
        if self.frames and frame.step < self.frames[-1].step:
            self.clear()
        if self.frames and frame.step == self.frames[-1].step:
            self.frames[-1] = frame
        else:
            self.frames.append(frame)
        while len(self.frames) > self.limit:
            self.frames.popleft()
        return frame

    def at(self, step):
        if not self.frames or step < self.frames[0].step or step > self.frames[-1].step:
            return None
        # Simulation steps are consecutive while capture is active; this
        # fallback also handles a capture that started mid-project.
        index = step - self.frames[0].step
        if 0 <= index < len(self.frames) and self.frames[index].step == step:
            return self.frames[index]
        return next((frame for frame in self.frames if frame.step == step), None)


@dataclass
class TraceNode:
    text: str
    ref: SignalRef | None = None
    children: list["TraceNode"] = field(default_factory=list)
    active: bool = False


@dataclass(frozen=True)
class WireEdge:
    id: str
    source: str
    source_pin: str
    target: str
    target_pin: str
    bit_index: int | None = None

    @property
    def ref(self):
        return SignalRef.wire_bit(self.id, self.bit_index) if self.bit_index is not None else SignalRef.wire(self.id)


class TraceAnalyzer:
    """Analyze one immutable observation against the existing Circuit graph."""
    MAX_NODES = 1200
    MAX_DEPTH = 80

    def __init__(self, circuit, frame, simulator, *, historical=False, block_stack=()):
        self.circuit, self.frame, self.simulator = circuit, frame, simulator
        self.historical = historical
        self.block_stack = block_stack
        self.drivers = {}
        self.fanout = {}
        for wire in circuit.wires.values():
            for index, (source_pin, target_pin) in enumerate(wire_bit_pairs(wire)):
                edge = WireEdge(wire.id, wire.source, source_pin, wire.target, target_pin,
                                index if isinstance(wire, BusWire) else None)
                self.drivers[wire.target, target_pin] = edge
                self.fanout.setdefault((wire.source, source_pin), []).append(edge)
        self.connected_components, self.connected_wires = set(), set()
        self.active_components, self.active_wires = set(), set()
        self.nodes_seen = 0

    def _pin(self, cid, pin, direction):
        return SignalRef.component_pin(cid, pin, direction)

    def _label(self, ref):
        if ref.kind in ("wire", "wire_bit"):
            wire = self.circuit.wires.get(ref.wire_id)
            if not wire:
                return "Deleted wire"
            if ref.kind == "wire_bit":
                index = int(ref.pin)
                return f"Bus bit {index}: {wire.source_bits[index]} → {self.circuit.components[wire.target].kind}.{wire.target_bits[index]}"
            if isinstance(wire, BusWire):
                return f"Bus {wire.source_pin}[{wire.width - 1}:0] → {self.circuit.components[wire.target].kind}.{wire.target_pin}"
            return f"Wire {wire.source_pin} → {self.circuit.components[wire.target].kind}.{wire.target_pin}"
        component = self.circuit.components.get(ref.component_id)
        return f"{component.kind if component else 'Deleted component'}.{ref.pin}"

    def _node(self, ref, active=False):
        self.nodes_seen += 1
        value = self.frame.value(ref, self.circuit)
        if ref.kind in ("wire", "wire_bit"):
            self.connected_wires.add(ref.wire_id)
            if active: self.active_wires.add(ref.wire_id)
        else:
            self.connected_components.add(ref.component_id)
            if active: self.active_components.add(ref.component_id)
        return TraceNode(f"{self._label(ref)} = {value_text(value)}", ref, active=active)

    @staticmethod
    def _tree_refs(node):
        if node.ref is not None:
            yield node.ref
        for child in node.children:
            yield from TraceAnalyzer._tree_refs(child)

    @staticmethod
    def _mapped_pin(target, direction):
        return (target, "Q" if direction == "input" else "A") if isinstance(target, str) else tuple(target)

    def _inner_block(self, component):
        name = component.kind[6:]
        if name in self.block_stack:
            raise ValueError("Recursive custom block reference")
        definition = self.circuit.blocks[name]
        inner = Circuit.from_dict(definition["circuit"])
        inner.tick = component.state.get("inner_tick", 0)
        Simulator._set_block_inputs(inner, definition, self.frame.inputs.get(component.id, {}))
        for cid, state in component.state.get("inner", {}).items():
            if cid in inner.components:
                inner.components[cid].state = deepcopy(state)
        inner_sim = Simulator(inner, self.block_stack + (name,))
        recorded = self.frame.block_events.get(component.id, {})
        inner_sim.last_transitions = deepcopy(recorded.get("transitions", {}))
        inner_sim.last_block_events = deepcopy(recorded.get("blocks", {}))
        return definition, inner, inner_sim

    def _block_inputs_for_output(self, component, output_pin):
        try:
            definition, inner, inner_sim = self._inner_block(component)
            cid, pin = self._mapped_pin(definition["output_map"][output_pin], "output")
            nested = TraceAnalyzer(inner, TraceFrame.from_simulator(inner_sim), inner_sim,
                                   block_stack=self.block_stack + (component.kind[6:],))
            reached = set(self._tree_refs(nested.backward(self._pin(cid, pin, "input"))))
            return [external for external, target in definition["input_map"].items()
                    if self._pin(*self._mapped_pin(target, "input"), "output") in reached]
        except (KeyError, ValueError, TypeError):
            return None

    def _block_outputs_for_input(self, component, input_pin):
        try:
            definition, inner, inner_sim = self._inner_block(component)
            cid, pin = self._mapped_pin(definition["input_map"][input_pin], "input")
            nested = TraceAnalyzer(inner, TraceFrame.from_simulator(inner_sim), inner_sim,
                                   block_stack=self.block_stack + (component.kind[6:],))
            reached = set(self._tree_refs(nested.forward(self._pin(cid, pin, "output"))))
            return [external for external, target in definition["output_map"].items()
                    if self._pin(*self._mapped_pin(target, "output"), "input") in reached]
        except (KeyError, ValueError, TypeError):
            return None

    def backward(self, ref):
        if not ref.valid(self.circuit):
            return TraceNode("Signal was deleted or its pin changed")
        visited = set()
        if ref.kind == "bus":
            node = self._node(ref, True)
            bits = bus_ports(self.circuit.components[ref.component_id], self.circuit.blocks)[ref.direction][ref.pin]
            for bit in bits:
                node.children.append(self.backward(self._pin(ref.component_id, bit, ref.direction)))
            return node
        if ref.kind in ("wire", "wire_bit"):
            node = self._node(ref, True)
            wire = self.circuit.wires[ref.wire_id]
            if isinstance(wire, BusWire):
                indices = range(wire.width) if ref.kind == "wire" else (int(ref.pin),)
                for index in indices:
                    node.children.append(self._back_output(wire.source, wire.source_bits[index], set(), True))
            else:
                node.children.append(self._back_output(wire.source, wire.source_pin, visited, True))
            return node
        if ref.direction == "input":
            return self._back_input(ref.component_id, ref.pin, visited, True)
        return self._back_output(ref.component_id, ref.pin, visited, True)

    def _back_input(self, cid, pin, visited, active, sampled=_NO_SAMPLE):
        if self.nodes_seen >= self.MAX_NODES or len(visited) >= self.MAX_DEPTH:
            return TraceNode("Trace depth/size limit reached; choose a nearer signal")
        ref = self._pin(cid, pin, "input")
        node = self._node(ref, active)
        if sampled is not _NO_SAMPLE:
            observed = self.frame.value(ref, self.circuit)
            node.text += f" · sampled {value_text(sampled)}"
            if sampled != observed:
                node.children.append(TraceNode("Current input differs from the sampled event; upstream value at sampling time is not in this frame"))
                return node
        if (cid, pin) in self.frame.forced_inputs:
            node.children.append(TraceNode("Input is temporarily forced here"))
            return node
        wire = self.drivers.get((cid, pin))
        if wire is None:
            node.children.append(TraceNode("Unconnected input"))
            return node
        wire_node = self._node(wire.ref, active)
        wire_node.children.append(self._back_output(wire.source, wire.source_pin, visited, active))
        node.children.append(wire_node)
        return node

    def _back_output(self, cid, pin, visited, active):
        if self.nodes_seen >= self.MAX_NODES or len(visited) >= self.MAX_DEPTH:
            return TraceNode("Trace depth/size limit reached; choose a nearer signal")
        ref = self._pin(cid, pin, "output")
        node = self._node(ref, active)
        key = (cid, pin)
        if key in visited:
            node.children.append(TraceNode("Cycle already visited"))
            return node
        visited.add(key)
        component = self.circuit.components[cid]
        if key in self.frame.forced_outputs:
            node.children.append(TraceNode("Output is temporarily forced here"))
        elif component.kind == "Register File":
            port = pin.split("_", 1)[0][1:] if pin.startswith("R") and "_" in pin else None
            node.children.append(TraceNode("Stored register word is read through this port; address wires select the word"))
            if port is not None:
                for input_pin in pins(component, self.circuit.blocks)[0]:
                    if input_pin.startswith(f"RA{port}_"):
                        node.children.append(self._back_input(cid, input_pin, visited, False))
            event = self.frame.transitions.get(cid, {})
            written = event.get("current", {}).get("last_write")
            previous_write = event.get("previous", {}).get("last_write")
            if written and written != previous_write:
                node.children.append(TraceNode(f"A write was captured at this step: register {written['address']} "
                                               f"{written['previous']}→{written['current']}"))
        elif component.kind in SEQUENTIAL:
            influences = self.input_influence(cid, pin)
            causal = [p for p, status in influences.items() if status in ("influences", "sufficient")]
            if causal:
                node.children.append(TraceNode("Stored state updated by these sampled inputs"))
                sampled = self.frame.transitions[cid].get("inputs", {})
                for input_pin in causal:
                    node.children.append(self._back_input(cid, input_pin, visited, active,
                                                          sampled.get(input_pin, _NO_SAMPLE)))
            else:
                node.children.append(TraceNode("Stored state; no causal input event captured at this step"))
        elif component.kind.startswith("BLOCK:"):
            node.children.append(TraceNode("Inside custom block; see Explain for internal logic"))
            inputs = self._block_inputs_for_output(component, pin)
            if inputs is None:
                node.children.append(TraceNode("Internal connectivity unavailable"))
            elif not inputs:
                node.children.append(TraceNode("No direct combinational input path; internal state may drive this output"))
            for input_pin in inputs or ():
                node.children.append(self._back_input(cid, input_pin, visited, False))
        else:
            influences = self.input_influence(cid, pin)
            for input_pin in pins(component, self.circuit.blocks)[0]:
                if self.nodes_seen >= self.MAX_NODES:
                    node.children.append(TraceNode("Trace size limit reached"))
                    break
                node.children.append(self._back_input(cid, input_pin, visited,
                                                       active and influences.get(input_pin) in ("influences", "sufficient")))
        visited.remove(key)
        return node

    def forward(self, ref):
        if not ref.valid(self.circuit):
            return TraceNode("Signal was deleted or its pin changed")
        visited = set()
        if ref.kind == "bus":
            node = self._node(ref, True)
            bits = bus_ports(self.circuit.components[ref.component_id], self.circuit.blocks)[ref.direction][ref.pin]
            for bit in bits:
                node.children.append(self.forward(self._pin(ref.component_id, bit, ref.direction)))
            return node
        if ref.kind in ("wire", "wire_bit"):
            wire = self.circuit.wires[ref.wire_id]
            node = self._node(ref, True)
            if isinstance(wire, BusWire):
                indices = range(wire.width) if ref.kind == "wire" else (int(ref.pin),)
                for index in indices:
                    node.children.append(self._forward_input(wire.target, wire.target_bits[index], set(), True))
            else:
                node.children.append(self._forward_input(wire.target, wire.target_pin, visited, True))
            return node
        if ref.direction == "input":
            return self._forward_input(ref.component_id, ref.pin, visited, True)
        return self._forward_output(ref.component_id, ref.pin, visited, True)

    def _forward_input(self, cid, pin, visited, active):
        if self.nodes_seen >= self.MAX_NODES or len(visited) >= self.MAX_DEPTH:
            return TraceNode("Trace depth/size limit reached; choose a nearer signal")
        ref = self._pin(cid, pin, "input")
        node = self._node(ref, active)
        key = (cid, pin, "input")
        if key in visited:
            node.children.append(TraceNode("Cycle already visited"))
            return node
        visited.add(key)
        component = self.circuit.components[cid]
        if component.kind == "Register File" and pin.startswith("RA"):
            port = pin[2:].split("_", 1)[0]
            for out in pins(component, self.circuit.blocks)[1]:
                if out.startswith(f"R{port}_"):
                    node.children.append(self._forward_output(cid, out, visited, False))
        elif component.kind in SEQUENTIAL:
            node.children.append(TraceNode("State boundary; outputs depend on a sampled event"))
        else:
            outputs = (self._block_outputs_for_input(component, pin) if component.kind.startswith("BLOCK:")
                       else pins(component, self.circuit.blocks)[1])
            if outputs is None:
                node.children.append(TraceNode("Internal connectivity unavailable"))
            elif not outputs and component.kind.startswith("BLOCK:"):
                node.children.append(TraceNode("No direct path through block, or an internal state boundary"))
            for out in outputs or ():
                if self.nodes_seen >= self.MAX_NODES:
                    node.children.append(TraceNode("Trace size limit reached"))
                    break
                influence = self.input_influence(cid, out).get(pin)
                out_active = active and influence in ("influences", "sufficient")
                node.children.append(self._forward_output(cid, out, visited, out_active))
        visited.remove(key)
        return node

    def _forward_output(self, cid, pin, visited, active):
        if self.nodes_seen >= self.MAX_NODES or len(visited) >= self.MAX_DEPTH:
            return TraceNode("Trace depth/size limit reached; choose a nearer signal")
        ref = self._pin(cid, pin, "output")
        node = self._node(ref, active)
        key = (cid, pin, "output")
        if key in visited:
            node.children.append(TraceNode("Cycle already visited"))
            return node
        visited.add(key)
        wires = self.fanout.get((cid, pin), ())
        if not wires:
            node.children.append(TraceNode("No downstream connection"))
        for wire in wires:
            if self.nodes_seen >= self.MAX_NODES:
                node.children.append(TraceNode("Trace size limit reached"))
                break
            child = self._node(wire.ref, active)
            child.children.append(self._forward_input(wire.target, wire.target_pin, visited, active))
            node.children.append(child)
        visited.remove(key)
        return node

    def input_influence(self, cid, output_pin):
        """Local sensitivity using the engine's own component computation."""
        component = self.circuit.components[cid]
        values = self.frame.inputs.get(cid, {})
        input_pins = pins(component, self.circuit.blocks)[0]
        if any(error.startswith("Combinational feedback loop:") and cid in error
               for error in self.simulator.errors):
            return {p: "unavailable" for p in input_pins}
        if component.kind in ANALOG:
            return {p: "unavailable" for p in input_pins}
        if component.kind in SEQUENTIAL:
            event = self.frame.transitions.get(cid)
            if not event or event.get("step") != self.frame.step:
                return {p: "unavailable" for p in input_pins}
            if component.kind == "ISA Control Unit":
                # Its outputs depend on retained microphase/operands. Treat the
                # captured transition as evidence, not every wired input as a cause.
                return {p: "unavailable" for p in input_pins}
            if event.get("event") == "simulation reset":
                return {p: "inactive" for p in input_pins}
            if component.kind in ("RAM", "SRAM", "DRAM", "EEPROM", "Flash Memory", "Register File"):
                return {p: "unavailable" for p in input_pins}
            if component.kind == "Program Counter" and event.get("reset"):
                return {p: "influences" if p == "RESET" else "inactive" for p in input_pins}
            if component.kind == "SR Latch":
                sampled = event.get("inputs", {})
                active = sampled.get("S") in (1, None) or sampled.get("R") in (1, None)
                return {p: "influences" if active else "inactive" for p in input_pins}
            if component.kind == "D Latch":
                enable = event.get("inputs", {}).get("E")
                return {p: "influences" if enable in (1, None) else "inactive" for p in input_pins}
            if component.kind in ("Binary Counter", "Up Counter", "Down Counter") and event.get("reset"):
                return {p: "influences" if p == "RESET" else "inactive" for p in input_pins}
            if not event.get("clock_edge"):
                return {p: "inactive" for p in input_pins}
            return {p: "influences" for p in input_pins}
        if component.kind.startswith("BLOCK:") or component.kind in ("INPUT", "CONST", "Clock Generator", "Oscillator"):
            return {p: "unavailable" for p in input_pins}
        if not input_pins:
            return {}
        result = {}
        for pin in input_pins:
            original = values.get(pin)
            low, high = dict(values), dict(values)
            low[pin], high[pin] = 0, 1
            try:
                low_result = self.simulator._compute(component, low).get(output_pin)
                high_result = self.simulator._compute(component, high).get(output_pin)
            except (KeyError, ValueError, TypeError):
                result[pin] = "unavailable"
                continue
            result[pin] = ("influences" if low_result != high_result else "inactive")
            if low_result is None and high_result is None:
                result[pin] = "indeterminate"
            # Multiple controlling inputs can each be sufficient even when
            # flipping one alone does not change the output (AND 0,0).
            if result[pin] == "inactive" and component.kind in ("AND", "NAND", "OR", "NOR"):
                relevant = output_pin == "Q" and pin in ("A", "B") or (
                    output_pin.startswith("Q") and output_pin[1:].isdigit()
                    and pin in ("A" + output_pin[1:], "B" + output_pin[1:]))
                controlling = 0 if component.kind in ("AND", "NAND") else 1
                if relevant and original == controlling:
                    result[pin] = "sufficient"
            if original is None and result[pin] == "influences":
                result[pin] = "unknown influence"
        return result

    def explain(self, ref):
        if not ref.valid(self.circuit):
            return ["Signal no longer exists in this circuit."]
        invalid = self.circuit.validate()
        if invalid:
            return [f"Step {self.frame.step}: circuit wiring is invalid; the simulator cannot establish a reliable cause: "
                    + "; ".join(invalid)]
        value = self.frame.value(ref, self.circuit)
        lines = [f"Step {self.frame.step}: {self._label(ref)} = {value_text(value)}."]
        if ref.kind == "bus":
            bits = bus_ports(self.circuit.components[ref.component_id], self.circuit.blocks)[ref.direction][ref.pin]
            lines.append(f"Bus bits are numbered from 0 (least significant) to {len(bits) - 1}.")
            for index, pin_name in enumerate(bits):
                lines.extend(self.explain(self._pin(ref.component_id, pin_name, ref.direction)))
            return lines
        if ref.kind == "wire" and isinstance(self.circuit.wires[ref.wire_id], BusWire):
            wire = self.circuit.wires[ref.wire_id]
            lines.append(f"{wire.width}-bit bus; bit 0 is least significant.")
            for index in range(wire.width):
                lines.extend(self.explain(SignalRef.wire_bit(wire.id, index)))
            return lines
        if ref.kind in ("wire", "wire_bit"):
            wire = self.circuit.wires[ref.wire_id]
            source_pin = wire.source_bits[int(ref.pin)] if ref.kind == "wire_bit" else wire.source_pin
            target_pin = wire.target_bits[int(ref.pin)] if ref.kind == "wire_bit" else wire.target_pin
            lines.append(f"This connection carries {source_pin} from {self.circuit.components[wire.source].kind} to {self.circuit.components[wire.target].kind}.{target_pin}.")
            ref = self._pin(wire.source, source_pin, "output")
        elif ref.direction == "input":
            if (ref.component_id, ref.pin) in self.frame.forced_inputs:
                lines.append("This input is temporarily forced by a canvas tool.")
                return lines
            wire = self.drivers.get((ref.component_id, ref.pin))
            if wire is None:
                lines.append("No wire drives this input; its value is X.")
                return lines
            lines.append(f"Driven by {self.circuit.components[wire.source].kind}.{wire.source_pin} through wire {wire.id}.")
            ref = self._pin(wire.source, wire.source_pin, "output")
            lines.append(f"Source {self._label(ref)} = {value_text(self.frame.value(ref, self.circuit))}.")
        cid, pin = ref.component_id, ref.pin
        component = self.circuit.components[cid]
        kind = component.kind
        if (cid, pin) in self.frame.forced_outputs:
            lines.append("This output is temporarily forced by a canvas tool.")
            return lines
        if kind in ("INPUT", "CONST", "Bus Input"):
            lines.append("The source component supplies this observed value.")
            if self.historical:
                lines.append("Historical source settings were not captured; the displayed value is the recorded output.")
        elif kind in ("Clock Generator", "Oscillator"):
            if self.historical:
                lines.append("Clock output was captured at this step; historical period/running settings were not captured.")
            else:
                period = max(2, int(component.params.get("period", 4)))
                lines.append(f"The existing clock model uses period {period} simulation steps; phase {self.frame.step % period}, running={bool(component.params.get('running', True))}.")
        elif kind in SEQUENTIAL:
            lines.extend(self._explain_sequential(component, pin, value))
        elif kind in ANALOG:
            lines.append("This analog component is visual only; no electrical behavior is simulated.")
        elif kind.startswith("BLOCK:"):
            lines.extend(self._explain_block(component, pin))
        else:
            inputs = self.frame.inputs.get(cid, {})
            if inputs:
                lines.append("Observed inputs: " + ", ".join(f"{p}={value_text(v)}" for p, v in inputs.items()) + ".")
            influences = self.input_influence(cid, pin)
            for input_pin in pins(component, self.circuit.blocks)[0]:
                state = influences.get(input_pin, "unavailable")
                if state == "influences":
                    lines.append(f"{input_pin}={value_text(inputs.get(input_pin))} influences this output: changing it alone changes the computed result.")
                elif state == "sufficient":
                    lines.append(f"{input_pin}={value_text(inputs.get(input_pin))} is sufficient to force this output; another controlling input also holds it, so changing this input alone does not change the result.")
                elif state == "inactive":
                    lines.append(f"{input_pin}={value_text(inputs.get(input_pin))} is connected but changing it alone leaves this output unchanged at the other observed inputs.")
                elif state == "unknown influence":
                    lines.append(f"{input_pin}=X may determine this output; replacing X by 0 or 1 gives different results.")
                elif state == "indeterminate":
                    lines.append(f"Influence of {input_pin} cannot be determined while other required values are X.")
                else:
                    lines.append(f"Influence of {input_pin} is unavailable.")
            if value is None and any("feedback loop" in error.lower() for error in self.simulator.errors):
                lines.append("The simulator reported a combinational feedback loop; its output is X.")
            if kind not in LOGIC_GATES:
                lines.append("Influence is a local counterfactual at this step, not proof of an earlier transition cause.")
        return lines

    def _explain_sequential(self, component, pin, value):
        event = self.frame.transitions.get(component.id)
        if not event or event.get("step") != self.frame.step:
            return ["Stored output observed; sampled input and previous-state data are unavailable for this step."]
        if event.get("event") == "simulation reset":
            if component.kind in ("EEPROM", "Flash Memory"):
                return [f"Simulation reset restarted the tick while preserving nonvolatile memory; {pin} is now {value_text(value)}."]
            return [f"Simulation reset cleared the stored state; {pin} is now {value_text(value)}."]
        old, current, sampled = event["previous"], event["current"], event["inputs"]
        lines = []
        if component.kind == "ISA Control Unit":
            before, after = old.get("phase", "FETCH"), current.get("phase", "FETCH")
            lines.append(f"Recorded microphase {before}→{after} at simulation step {self.frame.step}.")
            if event.get("clock_edge"):
                lines.append("A clock edge advanced the ISA control state.")
            if before == "DECODE":
                opcode = current.get("opcode")
                lines.append(f"Instruction Register supplied opcode {value_text(opcode)}.")
            elif before in ("ARG1", "ARG2"):
                key = "arg1" if before == "ARG1" else "arg2"
                lines.append(f"ROM operand was captured as {value_text(current.get(key))}.")
            if current.get("last_completed") != old.get("last_completed"):
                record = current["last_completed"]
                lines.append(f"{record['mnemonic']} at address 0x{record['address']:02X} completed on this step.")
            if current.get("fault"):
                lines.append("CPU fault: " + current["fault"])
            lines.append(f"{pin} was recorded as {value_text(value)}. The path to this output is a control decision at the captured microphase.")
            return lines
        if component.kind == "Register File":
            port = pin.split("_", 1)[0][1:] if pin.startswith("R") and "_" in pin else None
            if port is not None:
                address_bits = [sampled.get(name) for name in pins(component, self.circuit.blocks)[0]
                                if name.startswith(f"RA{port}_")]
                address = None if None in address_bits else sum(bit << i for i, bit in enumerate(address_bits))
                lines.append(f"Read port {port} selected address {value_text(address)}; output {pin} was captured as {value_text(value)}.")
            write = current.get("last_write")
            if write and write != old.get("last_write"):
                lines.append(f"At this step, register {write['address']} was written: "
                             f"{value_text(write['previous'])}→{value_text(write['current'])}.")
            else:
                lines.append("No new register write was captured at this step.")
            lines.append("The trace frame records the output and write event, not every stored register word.")
            return lines
        if component.kind in ("RAM", "SRAM", "DRAM", "EEPROM", "Flash Memory"):
            address_bits = [sampled.get(name) for name in pins(component, self.circuit.blocks)[0]
                            if name.startswith("A") and name[1:].isdigit()]
            address = None if None in address_bits else sum(bit << i for i, bit in enumerate(address_bits))
            lines.append(f"Address {value_text(address)} was sampled; {pin} was captured as {value_text(value)}.")
            write = current.get("last_write")
            if write and write != old.get("last_write"):
                lines.append(f"Memory word {write['address']} changed "
                             f"{value_text(write['previous'])}→{value_text(write['current'])} at this step.")
            lines.append("This frame does not retain every historical memory word; further internal cause is unavailable.")
            return lines
        if component.kind in ("Binary Counter", "Up Counter", "Down Counter") and event.get("reset"):
            lines.append("RESET was sampled at 1 and took priority over the clock.")
        elif "CLK" in sampled:
            edge = component.params.get("edge", "rising")
            before = value_text(old.get("last_clk", 0) if old.get("last_clk") is not None else 0)
            now = value_text(sampled["CLK"])
            if event.get("clock_edge"):
                lines.append(f"A {edge} clock edge was sampled (CLK {before}→{now}).")
            else:
                lines.append(f"No {edge} clock edge was sampled (CLK {before}→{now}); clocked state was retained unless another control applied.")
        if component.kind == "D Flip-Flop" and event.get("clock_edge"):
            lines.append(f"D was sampled as {value_text(sampled.get('D'))}; stored Q changed {value_text(old.get('q', 0))}→{value_text(current.get('q', 0))}.")
        elif component.kind == "Register" and event.get("clock_edge"):
            bits = [sampled.get(f"D{i}") for i in range(len(pins(component, self.circuit.blocks)[1]))]
            lines.append("D bits sampled: " + "".join(value_text(v) for v in reversed(bits)) + f"; stored value changed {old.get('value', 0)}→{current.get('value', 0)}.")
        elif component.kind in ("Binary Counter", "Up Counter", "Down Counter"):
            lines.append(f"Stored count changed {old.get('value', 0)}→{current.get('value', 0)}; {pin}={value_text(value)}.")
        else:
            lines.append("Sampled inputs: " + ", ".join(f"{p}={value_text(v)}" for p, v in sampled.items()) + ".")
            lines.append(f"Stored state changed {old}→{current}; {pin}={value_text(value)}.")
        return lines

    def _explain_block(self, component, pin):
        if self.historical:
            return ["The block's external value was captured, but a complete historical internal signal snapshot was not retained; internal cause is unavailable."]
        name = component.kind[6:]
        if name in self.block_stack:
            return ["Recursive custom block reference; internal trace stopped."]
        try:
            definition, inner, inner_sim = self._inner_block(component)
            target = definition["output_map"][pin]
            target_cid, target_pin = (target, "A") if isinstance(target, str) else target
            nested = TraceAnalyzer(inner, TraceFrame.from_simulator(inner_sim), inner_sim,
                                   block_stack=self.block_stack + (name,))
            detail = nested.explain(SignalRef.component_pin(target_cid, target_pin, "input"))
            return [f"Inside {name}: {line}" for line in detail]
        except (KeyError, ValueError, TypeError) as error:
            return [f"Internal trace unavailable: {error}"]
