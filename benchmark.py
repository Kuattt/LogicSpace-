"""Measure the existing Simulator without changing its evaluation rules."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from app_paths import user_data_dir
from time import perf_counter_ns
import csv
import json
import platform
import os
import tempfile

from engine import BusWire, Circuit, Simulator
from cpu_board import create_cpu_circuit


PRESETS = {
    "logic_100": "100 logic gates",
    "logic_500": "500 logic gates",
    "logic_1000": "1000 logic gates",
    "combinational": "Large combinational circuit",
    "registers": "Registers and clock",
    "ram": "RAM read/write network",
    "cpu": "ISA 2.1 CPU execution",
}


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    components: int
    connections: int
    bus_wires: int
    requested_steps: int
    completed_steps: int
    build_seconds: float
    simulation_seconds: float
    average_step_seconds: float
    signal_changes: int
    cancelled: bool
    platform: str
    note: str = "Local logical-simulator measurement; do not compare across machines without matching environment and settings."

    def to_dict(self):
        return asdict(self)


def build_preset(name):
    if name not in PRESETS: raise ValueError("Unknown benchmark preset")
    if name == "cpu":
        return create_cpu_circuit("MOV R0, 1\nLOOP: ADD R0, R0\nJMP LOOP\n")
    c = Circuit()
    clock = c.add("Clock Generator", -300, 0, {"period": 2})
    if name.startswith("logic_"):
        count = int(name.split("_")[1])
        previous = clock
        for index in range(count):
            gate = c.add("NOT", (index % 50) * 180, (index // 50) * 120)
            c.connect(previous.id, "Q", gate.id, "A")
            previous = gate
    elif name == "combinational":
        for branch in range(16):
            previous = clock
            other = c.add("CONST", -220, branch * 110, {"value": branch & 1})
            for index in range(16):
                gate = c.add("XOR" if index % 2 else "AND", index * 170, branch * 110)
                c.connect(previous.id, "Q", gate.id, "A")
                c.connect(other.id, "Q", gate.id, "B")
                previous = gate
    elif name == "registers":
        data = c.add("Bus Input", -240, 100, {"width": 8, "value": 0xA5})
        for index in range(64):
            reg = c.add("Register", (index % 16) * 220, (index // 16) * 160, {"width": 8})
            c.connect_bus(data.id, "Q", reg.id, "D")
            c.connect(clock.id, "Q", reg.id, "CLK")
    elif name == "ram":
        address = c.add("Bus Input", -280, 100, {"width": 4, "value": 3})
        data = c.add("Bus Input", -280, 200, {"width": 8, "value": 0x5A})
        write = c.add("CONST", -280, 300, {"value": 1})
        for index in range(16):
            ram = c.add("RAM", (index % 8) * 240, (index // 8) * 280,
                        {"address_bits": 4, "data_bits": 8, "depth": 16})
            c.connect_bus(address.id, "Q", ram.id, "A")
            c.connect_bus(data.id, "Q", ram.id, "D")
            c.connect(write.id, "Q", ram.id, "WE")
            c.connect(clock.id, "Q", ram.id, "CLK")
    return c


def run_benchmark(name, steps=20, circuit_factory=None, cancelled=None):
    if type(steps) is not int or not 1 <= steps <= 10000:
        raise ValueError("Benchmark steps must be 1–10000")
    start = perf_counter_ns()
    circuit = circuit_factory() if circuit_factory is not None else build_preset(name)
    simulator = Simulator(circuit)
    if simulator.errors: raise ValueError("Benchmark circuit is invalid: " + "; ".join(simulator.errors))
    build_seconds = (perf_counter_ns() - start) / 1e9
    simulation_ns = 0
    signal_changes = 0
    completed = 0
    for _ in range(steps):
        if cancelled and cancelled(): break
        before = simulator.outputs.copy()
        tick_start = perf_counter_ns()
        simulator.step()
        simulation_ns += perf_counter_ns() - tick_start
        if simulator.errors: raise ValueError("Benchmark simulation failed: " + "; ".join(simulator.errors))
        signal_changes += sum(before.get(key) != value for key, value in simulator.outputs.items())
        completed += 1
    simulation_seconds = simulation_ns / 1e9
    return BenchmarkResult(name, len(circuit.components), len(circuit.wires),
                           sum(isinstance(wire, BusWire) for wire in circuit.wires.values()),
                           steps, completed, build_seconds, simulation_seconds,
                           simulation_seconds / completed if completed else 0.0,
                           signal_changes, completed < steps,
                           f"{platform.system()} {platform.release()} · Python {platform.python_version()}")


def export_json(result, path):
    Path(path).write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def export_csv(result, path):
    data = result.to_dict()
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data))
        writer.writeheader(); writer.writerow(data)


class BenchmarkHistory:
    """Bounded local run history; comparisons require identical scenario/settings."""
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else user_data_dir() / "benchmark_history.json"

    def read(self):
        if not self.path.exists(): return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or data.get("format") != "logicspace-benchmark-history" or
                data.get("version") != 1 or not isinstance(data.get("runs"), list) or
                len(data["runs"]) > 100):
            raise ValueError("Invalid benchmark history")
        return [BenchmarkResult(**item) for item in data["runs"]]

    @staticmethod
    def comparable(previous, current):
        fields = ("name", "components", "connections", "bus_wires",
                  "requested_steps", "completed_steps", "platform")
        return not previous.cancelled and not current.cancelled and all(
            getattr(previous, field) == getattr(current, field) for field in fields)

    def record(self, result):
        retained = self.read()
        previous = next((item for item in reversed(retained)
                         if self.comparable(item, result)), None)
        runs = (retained + [result])[-100:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"format": "logicspace-benchmark-history", "version": 1,
                   "runs": [run.to_dict() for run in runs]}
        descriptor, temporary = tempfile.mkstemp(prefix=".benchmark-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        return previous
