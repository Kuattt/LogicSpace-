"""Project testbenches executed on an isolated copy by the LogicSpace Simulator."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from time import perf_counter
import uuid

from engine import Circuit, Simulator, ANALOG, BusWire, bus_ports, bit_width, pins
from timing_model import SignalRef, TimingHistory
from tracing_model import TraceFrame
from time_travel_model import SimulationSnapshot, topology_key

SCHEMA_VERSION = 1
DEFAULT_MAX_TESTBENCHES = 64
DEFAULT_MAX_STEPS = 2000
HARD_MAX_TESTBENCHES = 256
HARD_MAX_STEPS = 10000
MAX_SIGNALS = 128
MAX_FAILURE_SNAPSHOTS = 128
ASSERTION_KINDS = {"equals", "not_equals", "stable", "changes_after", "equals_at", "all_equal"}


def new_id():
    return uuid.uuid4().hex


def empty_package():
    return {"version": SCHEMA_VERSION, "limits": {"max_testbenches": DEFAULT_MAX_TESTBENCHES,
                                                   "max_steps": DEFAULT_MAX_STEPS}, "items": []}


def new_testbench(name="New Testbench"):
    return {"id": new_id(), "name": name, "signals": [], "steps": [{"drive": {}, "expect": {}, "repeat": 1}],
            "assertions": [], "stop_on_failure": False}


def signal_ref_dict(ref):
    if ref.kind in ("wire", "wire_bit"):
        if ref.kind == "wire_bit":
            return {"kind": "wire_bit", "wire_id": ref.wire_id, "index": int(ref.pin)}
        return {"kind": "wire", "wire_id": ref.wire_id}
    if ref.kind == "bus":
        return {"kind": "bus", "component_id": ref.component_id, "port": ref.pin,
                "direction": ref.direction}
    return {"kind": "pin", "component_id": ref.component_id, "pin": ref.pin, "direction": ref.direction}


def signal_ref_from_dict(data):
    if not isinstance(data, dict):
        raise ValueError("Signal reference must be an object")
    if data.get("kind") == "wire" and isinstance(data.get("wire_id"), str):
        return SignalRef.wire(data["wire_id"])
    if (data.get("kind") == "wire_bit" and isinstance(data.get("wire_id"), str)
            and type(data.get("index")) is int and data["index"] >= 0):
        return SignalRef.wire_bit(data["wire_id"], data["index"])
    if (data.get("kind") == "bus" and isinstance(data.get("component_id"), str)
            and isinstance(data.get("port"), str) and data.get("direction") in ("input", "output")):
        return SignalRef.bus_port(data["component_id"], data["port"], data["direction"])
    if (data.get("kind") == "pin" and isinstance(data.get("component_id"), str)
            and isinstance(data.get("pin"), str) and data.get("direction") in ("input", "output")):
        return SignalRef.component_pin(data["component_id"], data["pin"], data["direction"])
    raise ValueError("Invalid signal reference")


def _bit(value, context):
    if value is None or type(value) is int and value in (0, 1):
        return value
    raise ValueError(f"{context}: use 0, 1 or X")


def signal_width(circuit, ref):
    if ref.kind == "bus":
        component = circuit.components[ref.component_id]
        return len(bus_ports(component, circuit.blocks)[ref.direction][ref.pin])
    if ref.kind == "wire" and isinstance(circuit.wires.get(ref.wire_id), BusWire):
        return circuit.wires[ref.wire_id].width
    return 1


def normalize_value(value, width, context="Signal"):
    if width == 1:
        return _bit(value, context)
    if value is None:
        return tuple(None for _ in range(width))
    if type(value) is int and 0 <= value < 1 << width:
        return tuple((value >> index) & 1 for index in range(width))
    if (isinstance(value, (list, tuple)) and len(value) == width and
            all(bit is None or type(bit) is int and bit in (0, 1) for bit in value)):
        return tuple(value)
    raise ValueError(f"{context}: use a {width}-bit value or {width} bits ordered from bit 0; X is null")


def has_unknown(value):
    return value is None or isinstance(value, (tuple, list)) and None in value


def _nonnegative(value, context):
    if type(value) is not int or value < 0:
        raise ValueError(f"{context} must be a nonnegative integer")
    return value


def _signal_map(bench):
    return {entry["id"]: entry for entry in bench["signals"]}


def validate_package(circuit, package, *, allow_missing_refs=False):
    """Validate JSON data. Missing circuit pins can be retained for repair."""
    if not isinstance(package, dict) or package.get("version") != SCHEMA_VERSION:
        raise ValueError("Testbenches: unsupported or missing schema version")
    limits = package.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("Testbenches: limits must be an object")
    count = limits.get("max_testbenches")
    steps_limit = limits.get("max_steps")
    if type(count) is not int or not 1 <= count <= HARD_MAX_TESTBENCHES:
        raise ValueError(f"Testbenches: max_testbenches must be 1–{HARD_MAX_TESTBENCHES}")
    if type(steps_limit) is not int or not 1 <= steps_limit <= HARD_MAX_STEPS:
        raise ValueError(f"Testbenches: max_steps must be 1–{HARD_MAX_STEPS}")
    items = package.get("items")
    if not isinstance(items, list) or len(items) > count:
        raise ValueError("Testbenches: too many items or invalid item list")
    issues, seen_ids, seen_names = [], set(), set()
    for bench in items:
        if not isinstance(bench, dict):
            raise ValueError("Testbench entry must be an object")
        name, bench_id = bench.get("name"), bench.get("id")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("Testbench needs a name of 1–120 characters")
        if not isinstance(bench_id, str) or not bench_id or len(bench_id) > 128 or bench_id in seen_ids:
            raise ValueError(f"{name}: missing or duplicate testbench ID")
        if name.casefold() in seen_names:
            raise ValueError(f"Duplicate testbench name: {name}")
        seen_ids.add(bench_id); seen_names.add(name.casefold())
        if type(bench.get("stop_on_failure", False)) is not bool:
            raise ValueError(f"{name}: stop_on_failure must be true or false")
        signals = bench.get("signals")
        if not isinstance(signals, list) or len(signals) > MAX_SIGNALS:
            raise ValueError(f"{name}: signals must be a list of at most {MAX_SIGNALS}")
        signal_ids, role_refs = set(), set()
        for entry in signals:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
                raise ValueError(f"{name}: signal needs an ID")
            signal_id, role = entry["id"], entry.get("role")
            if signal_id in signal_ids or role not in ("drive", "observe"):
                raise ValueError(f"{name}: duplicate signal ID or invalid role")
            signal_ids.add(signal_id)
            ref = signal_ref_from_dict(entry.get("ref"))
            if (role, ref) in role_refs:
                raise ValueError(f"{name}: same {role} signal selected twice")
            role_refs.add((role, ref))
            valid = ref.valid(circuit)
            if valid and role == "drive":
                component = circuit.components.get(ref.component_id)
                valid = (ref.kind in ("pin", "bus") and ref.direction == "output"
                         and component.kind in ("INPUT", "CONST", "Bus Input"))
            if valid and role == "observe" and ref.kind in ("pin", "bus"):
                valid = circuit.components[ref.component_id].kind not in ANALOG
            if not valid:
                message = f"{name}: {role} signal {signal_id} references a missing or unsupported pin"
                if allow_missing_refs:
                    issues.append(message)
                else:
                    raise ValueError(message)
        by_id = _signal_map(bench)
        steps = bench.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"{name}: add at least one step")
        expanded = 0
        for index, row in enumerate(steps):
            if not isinstance(row, dict):
                raise ValueError(f"{name}: step {index} must be an object")
            repeat = row.get("repeat", 1)
            if type(repeat) is not int or not 1 <= repeat <= steps_limit:
                raise ValueError(f"{name}: step {index} repeat must be 1–{steps_limit}")
            expanded += repeat
            if expanded > steps_limit:
                raise ValueError(f"{name}: sequence exceeds {steps_limit} simulation steps")
            for field, role in (("drive", "drive"), ("expect", "observe")):
                values = row.get(field, {})
                if not isinstance(values, dict):
                    raise ValueError(f"{name}: step {index} {field} must be an object")
                for signal_id, value in values.items():
                    if signal_id not in by_id or by_id[signal_id]["role"] != role:
                        raise ValueError(f"{name}: step {index} has unknown {role} signal {signal_id}")
                    ref = signal_ref_from_dict(by_id[signal_id]["ref"])
                    if ref.valid(circuit):
                        normalize_value(value, signal_width(circuit, ref), f"{name} step {index} {signal_id}")
        assertions = bench.get("assertions", [])
        if not isinstance(assertions, list) or len(assertions) > steps_limit:
            raise ValueError(f"{name}: invalid assertion list")
        assertion_ids = set()
        for assertion in assertions:
            if not isinstance(assertion, dict) or assertion.get("kind") not in ASSERTION_KINDS:
                raise ValueError(f"{name}: unknown assertion type")
            assertion_id = assertion.get("id")
            if not isinstance(assertion_id, str) or not assertion_id or assertion_id in assertion_ids:
                raise ValueError(f"{name}: duplicate or missing assertion ID")
            assertion_ids.add(assertion_id)
            kind = assertion["kind"]
            if kind == "all_equal":
                values = assertion.get("values")
                if not isinstance(values, dict) or len(values) < 2:
                    raise ValueError(f"{name}: all_equal needs at least two output values")
                for signal_id, value in values.items():
                    if signal_id not in by_id or by_id[signal_id]["role"] != "observe":
                        raise ValueError(f"{name}: all_equal references an unknown output")
                    ref = signal_ref_from_dict(by_id[signal_id]["ref"])
                    if ref.valid(circuit):
                        normalize_value(value, signal_width(circuit, ref), f"{name} all_equal")
            else:
                signal_id = assertion.get("signal")
                if signal_id not in by_id or by_id[signal_id]["role"] != "observe":
                    raise ValueError(f"{name}: assertion references an unknown output")
            if kind in ("equals", "not_equals", "equals_at"):
                ref = signal_ref_from_dict(by_id[assertion["signal"]]["ref"])
                if ref.valid(circuit):
                    normalize_value(assertion.get("value", "missing"), signal_width(circuit, ref), f"{name} assertion value")
            if kind in ("equals_at", "all_equal") or "at" in assertion:
                at = _nonnegative(assertion.get("at"), f"{name} assertion step")
                if at >= expanded:
                    raise ValueError(f"{name}: assertion step is outside the sequence")
            if kind == "stable":
                start, end = _nonnegative(assertion.get("start"), "Stable start"), _nonnegative(assertion.get("end"), "Stable end")
                if start >= end or end >= expanded:
                    raise ValueError(f"{name}: stable range must cover at least two recorded steps")
            if kind == "changes_after":
                event = assertion.get("event_signal")
                if event not in by_id:
                    raise ValueError(f"{name}: event signal is not selected")
                event_ref = signal_ref_from_dict(by_id[event]["ref"])
                if event_ref.valid(circuit):
                    width = signal_width(circuit, event_ref)
                    normalize_value(assertion.get("from", "missing"), width, f"{name} event start")
                    normalize_value(assertion.get("to", "missing"), width, f"{name} event end")
                if assertion["from"] == assertion["to"]:
                    raise ValueError(f"{name}: event needs two different signal values")
                within = _nonnegative(assertion.get("within"), f"{name} event window")
                if within >= expanded:
                    raise ValueError(f"{name}: event window exceeds the sequence")
    return issues


@dataclass
class AssertionResult:
    status: str
    step: int | None
    signal_id: str | None
    expected: object
    actual: object
    message: str
    assertion_id: str = ""


@dataclass
class FailureSnapshot:
    circuit: Circuit
    frame: TraceFrame


@dataclass
class TestbenchResult:
    bench_id: str
    name: str
    outcomes: list[AssertionResult] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)
    expected_by_step: dict = field(default_factory=dict)
    snapshots: dict = field(default_factory=dict)
    time_snapshots: dict = field(default_factory=dict)
    previous_time_snapshots: dict = field(default_factory=dict)
    timing: TimingHistory | None = None
    duration_seconds: float = 0.0
    cancelled: bool = False
    signal_refs: dict = field(default_factory=dict)
    signal_labels: dict = field(default_factory=dict)
    stopped_early: bool = False

    @property
    def passed(self):
        return sum(item.status == "passed" for item in self.outcomes)

    @property
    def failed(self):
        return sum(item.status == "failed" for item in self.outcomes)

    @property
    def inconclusive(self):
        return sum(item.status == "inconclusive" for item in self.outcomes)

    @property
    def first_failure(self):
        failures = [item for item in self.outcomes if item.status == "failed"]
        return min(failures, key=lambda item: item.step if item.step is not None else 10**9) if failures else None


def compare_equal(actual, expected):
    if isinstance(actual, tuple):
        expected = normalize_value(expected, len(actual))
        if any(left is not None and right is not None and left != right
               for left, right in zip(actual, expected)):
            return "failed"
        if any(left is None and right is not None for left, right in zip(actual, expected)):
            return "inconclusive"
    if actual is None and expected is not None:
        return "inconclusive"
    return "passed" if actual == expected else "failed"


def compare_not_equal(actual, expected):
    if isinstance(actual, tuple):
        outcome = compare_equal(actual, expected)
        return "failed" if outcome == "passed" else ("passed" if outcome == "failed" else "inconclusive")
    if actual is None and expected is not None:
        return "inconclusive"
    return "passed" if actual != expected else "failed"


def _isolated_circuit(source):
    data = deepcopy(source.to_dict())
    data.pop("testbenches", None)
    cloned = Circuit.from_dict(data)
    cloned.tick = 0
    for component in cloned.components.values():
        if component.kind in ("EEPROM", "Flash Memory"):
            memory = deepcopy(component.state.get("memory", {}))
            component.state.clear()
            component.state["memory"] = memory
        else:
            component.state.clear()
    return cloned


class TestbenchSession:
    """One deterministic, cancellable execution; call advance in GUI sized batches."""
    def __init__(self, source, bench, *, max_steps=DEFAULT_MAX_STEPS):
        package = {"version": 1, "limits": {"max_testbenches": 1, "max_steps": max_steps},
                   "items": [bench]}
        validate_package(source, package)
        if not any(row.get("expect") for row in bench["steps"]) and not bench.get("assertions"):
            raise ValueError(f"{bench['name']}: add an expected output or assertion before running")
        self.bench = deepcopy(bench)
        self.circuit = _isolated_circuit(source)
        self.sim = Simulator(self.circuit)
        self.signals = _signal_map(bench)
        self.refs = {signal_id: signal_ref_from_dict(entry["ref"])
                     for signal_id, entry in self.signals.items()}
        self.rows = [(row, index) for index, row in enumerate(bench["steps"]) for _ in range(row.get("repeat", 1))]
        self.index = 0
        self.done = False
        self.started = perf_counter()
        self.result = TestbenchResult(bench["id"], bench["name"], signal_refs=self.refs,
                                      signal_labels={sid: ref.label(self.circuit) for sid, ref in self.refs.items()})
        self.result.timing = TimingHistory(limit=max(10, min(max_steps, HARD_MAX_STEPS)))
        for signal_id, ref in self.refs.items():
            self.result.timing.add(ref, self.sim, label=ref.label(self.circuit))
        self._evaluated_assertions = set()
        self._time_topology = topology_key(self.circuit)
        self._last_time_snapshot = None
        self._previous_time_snapshot = None
        self._current_time_snapshot = None

    def cancel(self):
        if not self.done:
            self.result.cancelled = True
            self._finish()

    def advance(self, count=1):
        for _ in range(max(1, count)):
            if self.done: break
            self._one_step()
        return self.done

    def run(self):
        while not self.done:
            self.advance(1)
        return self.result

    def _set_drive(self, signal_id, value):
        ref = self.refs[signal_id]
        component = self.circuit.components[ref.component_id]
        width = bit_width(component)
        if ref.kind == "bus":
            component.params["_bit_values"] = list(normalize_value(value, signal_width(self.circuit, ref)))
            return
        if width == 1:
            component.params["value"] = value
        else:
            values = component.params.get("_bit_values")
            if values is None:
                default = component.params.get("value", 0 if component.kind in ("INPUT", "Bus Input") else 1)
                values = [None if default is None else (int(default) >> bit) & 1 for bit in range(width)]
            values = list(values)
            values[int(ref.pin[1:])] = value
            component.params["_bit_values"] = values

    def _one_step(self):
        row, _source_row = self.rows[self.index]
        for signal_id, value in row.get("drive", {}).items():
            self._set_drive(signal_id, value)
        if self.index == 0:
            self.sim.evaluate()
            self.result.timing.clear_history(self.sim)
        else:
            self.sim.step()
            self.result.timing.record_step(self.sim)
        self._previous_time_snapshot = self._last_time_snapshot
        self._current_time_snapshot = SimulationSnapshot.capture(self.sim, self._time_topology,
                                                                  measure=False)
        observation = {signal_id: ref.value(self.sim) for signal_id, ref in self.refs.items()}
        self.result.observations.append(observation)
        self.result.expected_by_step[self.index] = {
            sid: normalize_value(expected, signal_width(self.circuit, self.refs[sid]))
            for sid, expected in row.get("expect", {}).items()}
        for signal_id, expected in row.get("expect", {}).items():
            actual = observation[signal_id]
            expected = self.result.expected_by_step[self.index][signal_id]
            status = compare_equal(actual, expected)
            self._add_result(AssertionResult(status, self.index, signal_id, expected, actual,
                                            f"Step {self.index}: expected {expected}, observed {actual}"))
        for assertion in self.bench.get("assertions", []):
            if assertion["id"] in self._evaluated_assertions:
                continue
            outcome = self._evaluate_assertion(assertion, final=self.index == len(self.rows) - 1)
            if outcome is not None:
                self._evaluated_assertions.add(assertion["id"])
                self._add_result(outcome)
        self.index += 1
        self._last_time_snapshot = self._current_time_snapshot
        if self.index >= len(self.rows) or (self.bench.get("stop_on_failure") and self.result.failed):
            self.result.stopped_early = self.index < len(self.rows) and not self.result.cancelled
            self._finish()

    def _add_result(self, outcome):
        self.result.outcomes.append(outcome)
        if outcome.status == "failed" and outcome.step is not None and outcome.step not in self.result.snapshots:
            if len(self.result.snapshots) < MAX_FAILURE_SNAPSHOTS:
                self.result.snapshots[outcome.step] = FailureSnapshot(
                    Circuit.from_dict(deepcopy(self.circuit.to_dict())), TraceFrame.from_simulator(self.sim))
                self.result.time_snapshots[outcome.step] = self._current_time_snapshot
                if self._previous_time_snapshot is not None:
                    self.result.previous_time_snapshots[outcome.step] = self._previous_time_snapshot

    def _outcome(self, assertion, status, step, signal_id, expected, actual, message):
        return AssertionResult(status, step, signal_id, expected, actual, message, assertion["id"])

    def _evaluate_assertion(self, assertion, *, final):
        kind = assertion["kind"]
        current = self.index
        observations = self.result.observations
        if kind in ("equals", "not_equals", "equals_at", "all_equal"):
            target_step = assertion.get("at", len(self.rows) - 1)
            if current < target_step:
                return None
            if kind == "all_equal":
                expected_values = {sid: normalize_value(expected, signal_width(self.circuit, self.refs[sid]))
                                   for sid, expected in assertion["values"].items()}
                statuses = {sid: compare_equal(observations[target_step][sid], expected)
                            for sid, expected in expected_values.items()}
                status = "failed" if "failed" in statuses.values() else (
                    "inconclusive" if "inconclusive" in statuses.values() else "passed")
                actual = {sid: observations[target_step][sid] for sid in assertion["values"]}
                self.result.expected_by_step[target_step].update(expected_values)
                relevant = next((sid for sid, result in statuses.items() if result == status),
                                next(iter(assertion["values"])))
                return self._outcome(assertion, status, target_step, relevant,
                                     expected_values, actual, "Multiple outputs checked together")
            signal_id = assertion["signal"]
            expected = normalize_value(assertion["value"], signal_width(self.circuit, self.refs[signal_id]))
            actual = observations[target_step][signal_id]
            status = compare_not_equal(actual, expected) if kind == "not_equals" else compare_equal(actual, expected)
            if kind != "not_equals":
                self.result.expected_by_step[target_step][signal_id] = expected
            return self._outcome(assertion, status, target_step, signal_id, expected, actual,
                                 f"{kind} at step {target_step}: expected {expected}, observed {actual}")
        if kind == "stable":
            start, end, signal_id = assertion["start"], assertion["end"], assertion["signal"]
            if current < start:
                return None
            values = [observations[step][signal_id] for step in range(start, min(current, end) + 1)]
            known = [value for value in values if not has_unknown(value)]
            if len(set(known)) > 1:
                return self._outcome(assertion, "failed", current, signal_id, values[0], values[-1],
                                     f"Signal changed during stable range {start}–{end}")
            if current < end:
                return None
            status = "inconclusive" if any(has_unknown(value) for value in values) else "passed"
            return self._outcome(assertion, status, end, signal_id, values[0], values[-1],
                                 f"Signal {'contains X' if status == 'inconclusive' else 'remained stable'} during {start}–{end}")
        if kind == "changes_after":
            event_id, target_id = assertion["event_signal"], assertion["signal"]
            window = assertion["within"]
            events = [step for step in range(1, len(observations))
                      if observations[step - 1][event_id] == normalize_value(assertion["from"], signal_width(self.circuit, self.refs[event_id]))
                      and observations[step][event_id] == normalize_value(assertion["to"], signal_width(self.circuit, self.refs[event_id]))]
            if not events:
                return (self._outcome(assertion, "inconclusive", current, target_id,
                                      "event", observations[current][target_id], "Specified event did not occur")
                        if final else None)
            for event_step in events:
                deadline = event_step + window
                if current < deadline and not final:
                    continue
                observed_until = min(current, deadline)
                baseline = observations[event_step - 1][target_id]
                changed = any(observations[step][target_id] != baseline
                              for step in range(event_step, observed_until + 1))
                if has_unknown(baseline) or any(has_unknown(observations[step][target_id])
                                           for step in range(event_step, observed_until + 1)):
                    return self._outcome(assertion, "inconclusive", event_step, target_id,
                                         "known transition", observations[observed_until][target_id],
                                         "Unknown output prevents a definite transition check")
                if not changed:
                    if observed_until < deadline:
                        return self._outcome(assertion, "inconclusive", event_step, target_id,
                                             "change", observations[observed_until][target_id],
                                             "Sequence ended before event window completed") if final else None
                    return self._outcome(assertion, "failed", deadline, target_id,
                                         "change", observations[deadline][target_id],
                                         f"No change within {window} steps after event at step {event_step}")
            if final:
                return self._outcome(assertion, "passed", events[0], target_id, "change",
                                     observations[current][target_id], f"Output changed after {len(events)} event(s)")
            return None
        return None

    def _finish(self):
        if self.done: return
        self.done = True
        self.result.duration_seconds = perf_counter() - self.started
        if self.result.cancelled or self.result.stopped_early:
            for assertion in self.bench.get("assertions", []):
                if assertion["id"] not in self._evaluated_assertions:
                    self.result.outcomes.append(self._outcome(assertion, "inconclusive", None,
                                                             assertion.get("signal"), "not run", None,
                                                             "Testbench was cancelled" if self.result.cancelled else
                                                             "Stopped after the first failure"))
