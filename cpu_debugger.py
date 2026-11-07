"""Instruction-level control and breakpoints over the existing Simulator."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import uuid

from cpu_board import validate_board, program_matches_rom
from cpu_architecture import get_active_binding
from cpu_isa import assemble


@dataclass
class CpuBreakpoint:
    id: str
    kind: str
    target: int
    expected: int | str | None = None
    enabled: bool = True


@dataclass(frozen=True)
class CpuBreakEvent:
    step: int
    breakpoint_id: str
    label: str
    before: object
    after: object
    reason: str
    address: int | None = None
    line: int | None = None


class CpuBreakpointManager:
    """Checks decoded instruction boundaries, register values and RAM access facts."""
    def __init__(self, limit=1000):
        self.items = {}
        self.events = deque(maxlen=max(10, int(limit)))
        self.last_count = 0
        self.last_phase = "FETCH"
        self.program = None
        self.source_sync = False
        self.binding = None

    def bind(self, circuit, binding=None):
        self.binding = binding if binding is not None else get_active_binding(circuit)
        ids = validate_board(circuit, self.binding)
        self.program = assemble(self.binding["source"])
        self.source_sync = program_matches_rom(circuit, self.program, self.binding)
        self.arm(circuit)
        return ids

    def arm(self, circuit):
        workspace = self.binding or get_active_binding(circuit) or {}
        controller = circuit.components.get(workspace.get("ids", {}).get("control"))
        state = controller.state if controller else {}
        self.last_count = state.get("instructions", 0)
        self.last_phase = state.get("phase", "FETCH")

    def add(self, kind, target, expected=None):
        if kind not in ("line", "address", "register", "memory"):
            raise ValueError("Choose line, address, register or memory breakpoint")
        if type(target) is not int or target < 0 or target > (3 if kind == "register" else 255):
            raise ValueError("Breakpoint target is outside its range")
        if kind == "line" and (self.program is None or
                               not any(row.line == target for row in self.program.listing)):
            raise ValueError("Choose a source line containing an assembled instruction")
        if kind == "register" and (type(expected) is not int or not 0 <= expected <= 255):
            raise ValueError("Register breakpoint value must be 0–255")
        if kind == "memory" and expected not in (None, "read", "write", "any"):
            raise ValueError("Memory access must be read, write or any")
        item = CpuBreakpoint(uuid.uuid4().hex, kind, target, expected)
        self.items[item.id] = item
        return item

    def remove(self, identifier):
        self.items.pop(identifier, None)

    def clear(self):
        self.items.clear()
        self.events.clear()

    def check(self, simulator):
        circuit = simulator.circuit
        if self.binding is None or self.program is None: return []
        try:
            self.source_sync = program_matches_rom(circuit, self.program, self.binding)
        except ValueError:
            self.program = None
            return []
        ids = self.binding["ids"]
        state = circuit.components[ids["control"]].state
        count = state.get("instructions", 0)
        phase = state.get("phase", "FETCH")
        entered_execute = phase == "EXEC" and self.last_phase != "EXEC"
        completed = count != self.last_count
        record = state.get("last_completed") if completed else None
        found = []
        for item in self.items.values():
            if not item.enabled: continue
            before = after = None
            address = state.get("current_pc") if entered_execute else record.get("address") if record else None
            line = self.program.address_to_line.get(address) if self.source_sync and address is not None else None
            matched = ((item.kind == "address" and entered_execute and address == item.target) or
                       (item.kind == "line" and entered_execute and line == item.target))
            if item.kind == "register" and completed:
                after = circuit.components[ids["registers"]].state.get("words", {}).get(str(item.target), 0)
                matched = after == item.expected
            if item.kind == "memory" and completed and record:
                memory = record.get("memory", {})
                matched = (memory.get("address") == item.target and
                           item.expected in (None, "any", memory.get("access")))
                after = memory.get("access")
            if matched:
                label = (f"Assembly line {item.target}" if item.kind == "line" else
                         f"Instruction 0x{item.target:02X}" if item.kind == "address" else
                         f"R{item.target} = {item.expected}" if item.kind == "register" else
                         f"RAM 0x{item.target:02X} {item.expected or 'any'}")
                found.append(CpuBreakEvent(circuit.tick, item.id, label, before, after,
                                           item.kind, address, line))
        self.last_count, self.last_phase = count, phase
        self.events.extend(found)
        return found


class CpuStepper:
    """Advances the supplied LogicSpace Simulator; never evaluates a separate CPU."""
    def __init__(self, simulator, advance=None, binding=None):
        self.simulator = simulator
        self.ids = validate_board(simulator.circuit, binding)
        self.advance = advance or simulator.step

    @property
    def state(self):
        return self.simulator.circuit.components[self.ids["control"]].state

    def step_clock_cycle(self, limit=20000, interrupted=None):
        if self.state.get("phase") == "HALT": return False
        for _ in range(limit):
            if interrupted and interrupted(): return False
            self.advance()
            event = self.simulator.last_transitions.get(self.ids["control"], {})
            if event.get("clock_edge") or self.state.get("phase") == "HALT":
                return True
        raise ValueError(f"No CPU clock edge in {limit} simulation steps")

    def step_instruction(self, limit=20000, interrupted=None):
        if self.state.get("phase") == "HALT": return False
        previous = self.state.get("instructions", 0)
        for _ in range(limit):
            if interrupted and interrupted(): return False
            self.advance()
            if self.state.get("instructions", 0) != previous or self.state.get("phase") == "HALT":
                return True
        raise ValueError(f"No completed instruction in {limit} simulation steps")

    def step_over(self, limit=20000, interrupted=None):
        depth = self.state.get("call_depth", 0)
        if not self.step_instruction(limit, interrupted): return False
        if self.state.get("call_depth", 0) <= depth: return True
        for _ in range(limit):
            if not self.step_instruction(limit, interrupted): return False
            if self.state.get("call_depth", 0) <= depth or self.state.get("phase") == "HALT":
                return True
        raise ValueError(f"CALL did not return within {limit} instructions")

    def step_out(self, limit=20000, interrupted=None):
        depth = self.state.get("call_depth", 0)
        if depth == 0: raise ValueError("Execution is not inside a CALL")
        for _ in range(limit):
            if not self.step_instruction(limit, interrupted): return False
            if self.state.get("call_depth", 0) < depth or self.state.get("phase") == "HALT":
                return True
        raise ValueError(f"RET was not reached within {limit} instructions")
