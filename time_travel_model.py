"""Bounded, GUI-independent simulation snapshots and branches for LogicSpace."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import pickle
import uuid

from engine import BusWire, pins
from timing_model import SignalRef
from tracing_model import TraceFrame

DEFAULT_LIMIT = 500
DEFAULT_MEMORY_MIB = 64
MAX_LIMIT = 10000
MAX_MEMORY_MIB = 1024
MAX_BRANCHES = 16
MAX_CHECKPOINTS = 64


def topology_key(circuit):
    """Ignore layout coordinates; include the pin interface and electrical graph."""
    components = tuple(sorted((cid, component.kind,
                               tuple(pins(component, circuit.blocks)[0]),
                               tuple(pins(component, circuit.blocks)[1]))
                              for cid, component in circuit.components.items()))
    wires = tuple(sorted((wid, wire.source, wire.source_pin, wire.target, wire.target_pin,
                          wire.width if isinstance(wire, BusWire) else 1,
                          tuple(wire.source_bits) if isinstance(wire, BusWire) else (),
                          tuple(wire.target_bits) if isinstance(wire, BusWire) else ())
                         for wid, wire in circuit.wires.items()))
    block_digest = hashlib.sha256(json.dumps(circuit.blocks, sort_keys=True,
                                             separators=(",", ":")).encode("utf-8")).hexdigest()
    return components, wires, block_digest


@dataclass(frozen=True)
class SimulationSnapshot:
    id: str
    step: int
    topology: tuple
    states: dict
    params: dict
    forced_inputs: dict
    forced_outputs: dict
    frame: TraceFrame
    errors: tuple
    size_bytes: int

    @classmethod
    def capture(cls, simulator, topology=None, *, measure=True):
        circuit = simulator.circuit
        states = {cid: deepcopy(component.state) for cid, component in circuit.components.items()}
        params = {cid: deepcopy(component.params) for cid, component in circuit.components.items()}
        frame = TraceFrame.from_simulator(simulator)
        forces_in, forces_out = deepcopy(simulator.forced_inputs), deepcopy(simulator.forced_outputs)
        errors = tuple(simulator.errors)
        data = (states, params, forces_in, forces_out, frame, errors)
        size = len(pickle.dumps(data, protocol=5)) if measure else 0
        return cls(uuid.uuid4().hex, circuit.tick, topology or topology_key(circuit), states, params,
                   forces_in, forces_out, frame, errors, size)

    def restore(self, simulator):
        circuit = simulator.circuit
        if topology_key(circuit) != self.topology:
            raise ValueError("Circuit structure changed; this simulation state cannot be restored")
        circuit.tick = self.step
        for cid, component in circuit.components.items():
            component.state = deepcopy(self.states[cid])
            component.params = deepcopy(self.params[cid])
        simulator.forced_inputs = deepcopy(self.forced_inputs)
        simulator.forced_outputs = deepcopy(self.forced_outputs)
        simulator.last_transitions = deepcopy(self.frame.transitions)
        simulator.last_block_events = deepcopy(self.frame.block_events)
        simulator.evaluate()
        if (simulator.inputs != self.frame.inputs or simulator.outputs != self.frame.outputs or
                tuple(simulator.errors) != self.errors):
            raise ValueError("Restored simulator values differ from the recorded state")


@dataclass
class Branch:
    id: str
    name: str
    states: OrderedDict[int, str]
    parent: str | None = None
    fork_step: int | None = None

    @property
    def first_step(self):
        return next(iter(self.states), None)

    @property
    def latest_step(self):
        return next(reversed(self.states), None) if self.states else None


@dataclass
class Checkpoint:
    id: str
    name: str
    branch_id: str
    snapshot_id: str
    step: int


@dataclass(frozen=True)
class StateDifference:
    category: str
    label: str
    before: object
    after: object
    component_id: str | None = None
    signal_ref: SignalRef | None = None

    @property
    def changed(self):
        return self.before != self.after


class SimulationHistory:
    """Shares immutable snapshots across branches and bounds total retained bytes."""
    def __init__(self, simulator, *, limit=DEFAULT_LIMIT, memory_mib=DEFAULT_MEMORY_MIB):
        self.limit = self._limit(limit)
        self.memory_limit = self._memory_limit(memory_mib)
        self.snapshots: OrderedDict[str, SimulationSnapshot] = OrderedDict()
        self.branches: OrderedDict[str, Branch] = OrderedDict()
        self.checkpoints: OrderedDict[str, Checkpoint] = OrderedDict()
        self.total_bytes = 0
        self.topology = topology_key(simulator.circuit)
        self.branch_number = 1
        self.active_branch = "main"
        self.cursor_id = ""
        self.reset(simulator)

    @staticmethod
    def _limit(value):
        if type(value) is not int or not 1 <= value <= MAX_LIMIT:
            raise ValueError(f"History limit must be 1–{MAX_LIMIT}")
        return value

    @staticmethod
    def _memory_limit(value):
        if type(value) is not int or not 1 <= value <= MAX_MEMORY_MIB:
            raise ValueError(f"Memory limit must be 1–{MAX_MEMORY_MIB} MiB")
        return value * 1024 * 1024

    @property
    def current(self):
        return self.snapshots.get(self.cursor_id)

    @property
    def branch(self):
        return self.branches[self.active_branch]

    @property
    def latest_step(self):
        return self.branch.latest_step

    @property
    def is_historical(self):
        return self.current is not None and self.current.step != self.latest_step

    def reset(self, simulator):
        self.snapshots.clear()
        self.branches.clear()
        self.checkpoints.clear()
        self.total_bytes = 0
        self.topology = topology_key(simulator.circuit)
        self.branch_number = 1
        self.active_branch = "main"
        self.branches["main"] = Branch("main", "Main", OrderedDict())
        self.cursor_id = ""
        self.record(simulator)

    def set_limits(self, *, limit=None, memory_mib=None):
        if limit is not None:
            self.limit = self._limit(limit)
        if memory_mib is not None:
            self.memory_limit = self._memory_limit(memory_mib)
        self._trim()

    def _store(self, snapshot):
        self.snapshots[snapshot.id] = snapshot
        self.total_bytes += snapshot.size_bytes
        self._trim()

    def _trim(self):
        while len(self.snapshots) > 1 and (len(self.snapshots) > self.limit or
                                           self.total_bytes > self.memory_limit):
            uid, old = self.snapshots.popitem(last=False)
            self.total_bytes -= old.size_bytes
            for branch in self.branches.values():
                if branch.states.get(old.step) == uid:
                    del branch.states[old.step]
            if self.cursor_id == uid:
                self.cursor_id = ""
        if not self.cursor_id:
            active = self.branches.get(self.active_branch)
            if not active or not active.states:
                replacement = next(((uid, branch) for uid, branch in reversed(self.branches.items())
                                    if branch.states), None)
                if replacement:
                    self.active_branch, active = replacement
            self.cursor_id = active.states[active.latest_step] if active and active.states else ""

    def matches(self, simulator):
        current = self.current
        if current is None or current.step != simulator.circuit.tick:
            return False
        if topology_key(simulator.circuit) != self.topology:
            return False
        if current.forced_inputs != simulator.forced_inputs or current.forced_outputs != simulator.forced_outputs:
            return False
        if current.frame.inputs != simulator.inputs or current.frame.outputs != simulator.outputs:
            return False
        return all(current.states[cid] == component.state and current.params[cid] == component.params
                   for cid, component in simulator.circuit.components.items())

    def record(self, simulator):
        if topology_key(simulator.circuit) != self.topology:
            self.reset(simulator)
            return self.current
        branch = self.branch
        if (branch.states and self.cursor_id in branch.states.values() and
                self.cursor_id != branch.states[branch.latest_step]):
            self.fork()
            branch = self.branch
        step = simulator.circuit.tick
        if branch.latest_step is not None and step < branch.latest_step:
            raise ValueError("Simulation step went backward without selecting a saved state")
        snapshot = SimulationSnapshot.capture(simulator, self.topology)
        old_id = branch.states.get(step)
        if old_id and old_id in self.snapshots:
            old = self.snapshots[old_id]
            if old.states == snapshot.states and old.params == snapshot.params and old.frame == snapshot.frame:
                self.cursor_id = old_id
                return old
            self.fork(include_current=False)
            branch = self.branch
        branch.states[step] = snapshot.id
        self.cursor_id = snapshot.id
        self._store(snapshot)
        return snapshot

    def fork(self, *, include_current=True):
        parent = self.branch
        current = self.current
        if current is None:
            raise ValueError("The selected simulation state has expired")
        prefix = OrderedDict((step, uid) for step, uid in parent.states.items()
                             if step < current.step or include_current and step == current.step)
        self.branch_number += 1
        uid = f"branch-{self.branch_number}"
        child = Branch(uid, f"Branch {self.branch_number}", prefix, parent.id, current.step)
        self.branches[uid] = child
        self.active_branch = uid
        if len(self.branches) > MAX_BRANCHES:
            removable = next((key for key in self.branches if key != self.active_branch), None)
            if removable:
                del self.branches[removable]
        return child

    def record_mutation(self, simulator):
        """Keep the old state on its branch when an input changes at the same tick."""
        if self.current is None or topology_key(simulator.circuit) != self.topology:
            self.reset(simulator)
            return self.current
        self.fork(include_current=False)
        return self.record(simulator)

    def available_steps(self, branch_id=None):
        branch = self.branches.get(branch_id or self.active_branch)
        return list(branch.states) if branch else []

    def navigate(self, simulator, step, branch_id=None):
        branch_id = branch_id or self.active_branch
        branch = self.branches.get(branch_id)
        if branch is None or step not in branch.states:
            raise ValueError(f"Simulation step {step} is unavailable in this branch")
        snapshot = self.snapshots.get(branch.states[step])
        if snapshot is None:
            raise ValueError(f"Simulation step {step} has expired")
        previous = self.current
        try:
            snapshot.restore(simulator)
        except ValueError:
            if previous is not None and previous.id != snapshot.id:
                try:
                    previous.restore(simulator)
                except ValueError:
                    pass
            raise
        self.active_branch = branch_id
        self.cursor_id = snapshot.id
        return snapshot

    def navigate_checkpoint(self, simulator, checkpoint_id):
        checkpoint = self.checkpoints.get(checkpoint_id)
        if not checkpoint or not self.checkpoint_available(checkpoint):
            raise ValueError("Checkpoint has expired or no longer exists")
        return self.navigate(simulator, checkpoint.step, checkpoint.branch_id)

    def checkpoint_available(self, checkpoint):
        branch = self.branches.get(checkpoint.branch_id)
        return bool(branch and checkpoint.snapshot_id in self.snapshots and
                    branch.states.get(checkpoint.step) == checkpoint.snapshot_id)

    def add_checkpoint(self, name):
        name = str(name).strip()
        if not name or len(name) > 80:
            raise ValueError("Checkpoint name must be 1–80 characters")
        if len(self.checkpoints) >= MAX_CHECKPOINTS:
            raise ValueError(f"Only {MAX_CHECKPOINTS} checkpoints can be kept")
        current = self.current
        if current is None:
            raise ValueError("No simulation state is selected")
        checkpoint = Checkpoint(uuid.uuid4().hex, name, self.active_branch, current.id, current.step)
        self.checkpoints[checkpoint.id] = checkpoint
        return checkpoint

    def rename_checkpoint(self, checkpoint_id, name):
        name = str(name).strip()
        if not name or len(name) > 80:
            raise ValueError("Checkpoint name must be 1–80 characters")
        self.checkpoints[checkpoint_id].name = name

    def delete_checkpoint(self, checkpoint_id):
        self.checkpoints.pop(checkpoint_id, None)

    def snapshot_at(self, branch_id, step):
        branch = self.branches.get(branch_id)
        uid = branch.states.get(step) if branch else None
        return self.snapshots.get(uid)

    def compare(self, circuit, first, second, *, include_unchanged=False):
        if first is None or second is None or first.topology != second.topology:
            raise ValueError("Both states must belong to the same circuit structure")
        differences = []

        def add(category, label, a, b, cid=None, ref=None):
            item = StateDifference(category, label, a, b, cid, ref)
            if include_unchanged or item.changed:
                differences.append(item)

        add("Time", "Simulation step", first.step, second.step)
        for cid, component in circuit.components.items():
            name = component.params.get("label") or component.kind
            before, after = first.states[cid], second.states[cid]
            for key in sorted(set(before) | set(after)):
                add("State", f"{name}.{key}", before.get(key, "<absent>"),
                    after.get(key, "<absent>"), cid)
            inputs, outputs = pins(component, circuit.blocks)
            for pin in inputs:
                ref = SignalRef.component_pin(cid, pin, "input")
                add("Pin", f"{name}.{pin} input", first.frame.value(ref, circuit),
                    second.frame.value(ref, circuit), cid, ref)
            for pin in outputs:
                ref = SignalRef.component_pin(cid, pin, "output")
                add("Pin", f"{name}.{pin} output", first.frame.value(ref, circuit),
                    second.frame.value(ref, circuit), cid, ref)
        for wid in circuit.wires:
            ref = SignalRef.wire(wid)
            add("Wire", ref.label(circuit), first.frame.value(ref, circuit),
                second.frame.value(ref, circuit), None, ref)
        return differences
