"""Behavior-checked lessons using isolated copies of the real LogicSpace Simulator."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import json

from engine import Circuit, Simulator
from cpu_architecture import discover_cpus
from cpu_board import create_cpu_circuit
from project_experience import APP_DATA, _atomic_json
from hdl_model import export_verilog, run_circuit_vectors, run_vectors


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    explanation: str
    task: str
    components: str
    completion: str


LESSONS = (
    Lesson("gates", "Logic Gates Fundamentals", "An AND output is high only when both inputs are high.",
           "Wire A and B to a circuit that produces A AND B at Y.", "INPUT A/B, AND or equivalent gates, OUTPUT Y", "All four AND cases match."),
    Lesson("adders", "Half Adder and Full Adder", "A full adder adds A, B and carry-in. With CIN=0 it is a half adder.",
           "Make SUM and COUT correct for all eight input combinations.", "INPUT A/B/CIN, Full Adder or gates, OUTPUT SUM/COUT", "Eight sum/carry cases match."),
    Lesson("arithmetic", "Binary Arithmetic", "A four-bit addition can overflow into a fifth carry bit.",
           "Connect 4-bit A and B, CIN, SUM and COUT.", "Bus Input A/B, INPUT CIN, Adder, Bus Output SUM, OUTPUT COUT", "Four arithmetic vectors match, including overflow."),
    Lesson("mux_decoder", "Multiplexers and Decoders", "A multiplexer chooses one data input; a decoder selects one address line.",
           "Wire Y as a two-way mux of A/B under SEL, and D0–D3 as a decoder of A/B.",
           "INPUT A/B/SEL, Multiplexer, Decoder, OUTPUT Y/D0–D3", "Mux and all decoder outputs match."),
    Lesson("sequential", "Flip-Flops and Registers", "A flip-flop and register capture input data on a rising clock edge.",
           "Store D in Q and four-bit DATA in REG only when CLK rises.",
           "INPUT D/CLK, Bus Input DATA, D Flip-Flop, Register, OUTPUT Q, Bus Output REG", "Both values hold and update on the correct edges."),
    Lesson("alu", "Building an ALU", "The operation bus selects arithmetic or bitwise results and flags.",
           "Build an 8-bit ALU with A, B, OP, RESULT, ZERO and CARRY.",
           "Bus Input A/B/OP, ALU, Bus Output RESULT, OUTPUT ZERO/CARRY", "ADD, SUB, AND and XOR results and flags match."),
    Lesson("ram", "RAM and Memory Addressing", "RAM writes on a rising clock edge when WE is high; reads use its address bus.",
           "Write DATA to ADDRESS 3, then prove address 4 is unchanged and address 3 retains it.",
           "Bus Input ADDRESS/DATA, INPUT WE/CLK, RAM, Bus Output Q", "Write/read sequence preserves both addresses."),
    Lesson("cpu", "Building an 8-bit CPU", "PC, ROM, IR, control, registers, ALU and RAM form one physical datapath.",
           "Build/bind an ISA 2.1 CPU and load MOV R0, 9 followed by HLT.",
           "ISA Control Unit, PC, ROM, IR, Register File, ALU, RAM, Clock and muxes", "Wiring validates and real execution leaves R0=9."),
    Lesson("isa", "Understanding the ISA 2.1", "CMP updates flags; JNZ uses the stored zero flag to repeat a loop.",
           "Program a loop using CMP and JNZ that halts with R0=3.",
           "Wired ISA 2.1 CPU with Assembly in ROM", "Actual execution takes JNZ and reaches R0=3."),
    Lesson("assembly", "Executing Assembly Instructions", "Assembly becomes ROM bytes; hardware reads, decodes and executes them.",
           "Run MOV R0,10; MOV R1,5; ADD R0,R1; STORE R0,0x20; HLT.",
           "Wired ISA 2.1 CPU, ROM, Register File, ALU, RAM", "R0=15 and RAM[0x20]=15 after real execution."),
)
LESSON_BY_ID = {lesson.id: lesson for lesson in LESSONS}


@dataclass(frozen=True)
class HDLLesson:
    id: str
    title: str
    explanation: str
    task: str
    starter: str
    vectors: tuple[dict, ...]
    mode: str = "hdl"


HDL_LESSONS = (
    HDLLesson("hdl_first", "Writing your first Verilog module", "assign connects logic to an output.",
              "Make y equal NOT a.", "module first(input a, output y);\n  // assign y here\nendmodule\n",
              ({"inputs": {"a": 0}, "expected": {"y": 1}}, {"inputs": {"a": 1}, "expected": {"y": 0}})),
    HDLLesson("hdl_comb", "Combinational logic in Verilog", "Bitwise expressions compile to real gates.",
              "Make y equal (a AND b) OR c.", "module comb(input a, input b, input c, output y);\n  // implement y\nendmodule\n",
              tuple({"inputs": {"a": a, "b": b, "c": c}, "expected": {"y": (a & b) | c}}
                    for a in (0, 1) for b in (0, 1) for c in (0, 1))),
    HDLLesson("hdl_mux", "Multiplexers in HDL", "The ?: operator selects one of two branches.",
              "Make y equal a when sel=0 and b when sel=1.",
              "module mux(input a, input b, input sel, output y);\n  // implement y\nendmodule\n",
              tuple({"inputs": {"a": a, "b": b, "sel": s}, "expected": {"y": b if s else a}}
                    for a in (0, 1) for b in (0, 1) for s in (0, 1))),
    HDLLesson("hdl_register", "Registers and sequential logic", "Registers sample data on a rising clock edge.",
              "On the canvas, wire INPUT D/CLK → D Flip-Flop → OUTPUT Q. Export it to see always @(posedge CLK).",
              "", ({"inputs": {"D": 1, "CLK": 0}, "expected": {"Q": 0}, "step": True},
                   {"inputs": {"D": 1, "CLK": 1}, "expected": {"Q": 1}, "step": True},
                   {"inputs": {"D": 0, "CLK": 1}, "expected": {"Q": 1}, "step": True},
                   {"inputs": {"D": 0, "CLK": 0}, "expected": {"Q": 1}, "step": True},
                   {"inputs": {"D": 0, "CLK": 1}, "expected": {"Q": 0}, "step": True}), "circuit"),
    HDLLesson("hdl_import", "HDL to LogicSpace conversion", "Imported HDL becomes editable LogicSpace components.",
              "Import an XOR module and verify all four input combinations.",
              "module xor2(input a, input b, output y);\n  // implement y\nendmodule\n",
              tuple({"inputs": {"a": a, "b": b}, "expected": {"y": a ^ b}}
                    for a in (0, 1) for b in (0, 1)), "import"),
    HDLLesson("hdl_export", "LogicSpace to HDL conversion", "Only components with exact HDL models can be exported.",
              "Build an AND circuit with INPUT a/b and OUTPUT y; export and verify its HDL.", "",
              tuple({"inputs": {"a": a, "b": b}, "expected": {"y": a & b}}
                    for a in (0, 1) for b in (0, 1)), "export"),
    HDLLesson("hdl_validation", "HDL simulation and validation", "Validation checks widths and tests actual outputs.",
              "Build a 4-bit adder: y = a + b. Verify overflow wraps to four bits.",
              "module add4(input [3:0] a, input [3:0] b, output [3:0] y);\n  // implement y\nendmodule\n",
              tuple({"inputs": {"a": a, "b": b}, "expected": {"y": (a + b) & 15}}
                    for a, b in ((0, 0), (3, 5), (15, 1), (12, 13))))
)
HDL_LESSON_BY_ID = {lesson.id: lesson for lesson in HDL_LESSONS}


def validate_hdl_lesson(circuit, lesson_id, source=""):
    if lesson_id not in HDL_LESSON_BY_ID: raise ValueError("Unknown HDL lesson")
    lesson = HDL_LESSON_BY_ID[lesson_id]
    try:
        if lesson.mode == "circuit":
            results = run_circuit_vectors(circuit, lesson.vectors)
            if "always @(posedge" not in export_verilog(circuit):
                raise ValueError("Exported circuit has no rising-edge register")
        elif lesson.mode == "export":
            results = run_circuit_vectors(circuit, lesson.vectors)
            generated = export_verilog(circuit)
            if "assign" not in generated: raise ValueError("Export has no combinational assignment")
        else:
            results = run_vectors(source, lesson.vectors)
            if lesson.mode == "import":
                results = run_circuit_vectors(circuit, lesson.vectors)
        failed = next((row for row in results if not row["passed"]), None)
        if failed:
            raise ValueError(f"Vector {failed['step']}: expected {failed['expected']}, actual {failed['actual']}")
        return LessonResult(True, f"Passed {len(results)} real simulation vectors.", len(results))
    except (ValueError, TypeError, KeyError, IndexError) as error:
        return LessonResult(False, str(error), 0)


@dataclass(frozen=True)
class LessonResult:
    passed: bool
    message: str
    checked: int = 0


def starter_circuit(lesson_id):
    if lesson_id not in LESSON_BY_ID: raise ValueError("Unknown lesson")
    if lesson_id == "cpu": return Circuit()
    if lesson_id in ("isa", "assembly"): return create_cpu_circuit("NOP\nHLT\n")
    c = Circuit()
    input_names = {
        "gates": ("A", "B"), "adders": ("A", "B", "CIN"),
        "arithmetic": ("A", "B", "CIN"),
        "mux_decoder": ("A", "B", "SEL"),
        "sequential": ("D", "CLK", "DATA"),
        "alu": ("A", "B", "OP"),
        "ram": ("ADDRESS", "DATA", "WE", "CLK"),
    }[lesson_id]
    output_names = {
        "gates": ("Y",), "adders": ("SUM", "COUT"),
        "arithmetic": ("SUM", "COUT"),
        "mux_decoder": ("Y", "D0", "D1", "D2", "D3"),
        "sequential": ("Q", "REG"),
        "alu": ("RESULT", "ZERO", "CARRY"),
        "ram": ("Q",),
    }[lesson_id]
    widths = {"arithmetic": {"A": 4, "B": 4, "SUM": 4},
              "sequential": {"DATA": 4, "REG": 4},
              "alu": {"A": 8, "B": 8, "OP": 4, "RESULT": 8},
              "ram": {"ADDRESS": 8, "DATA": 8, "Q": 8}}
    for index, name in enumerate(input_names):
        width = widths.get(lesson_id, {}).get(name, 1)
        kind = "Bus Input" if width > 1 else "INPUT"
        c.add(kind, -300, index * 135, {"label": name, "width": width, "value": 0})
    for index, name in enumerate(output_names):
        width = widths.get(lesson_id, {}).get(name, 1)
        kind = "Bus Output" if width > 1 else "OUTPUT"
        c.add(kind, 450, index * 135, {"label": name, "width": width})
    return c


def _interface(circuit, expected, kinds):
    mapping = {}
    for name in expected:
        matches = [component for component in circuit.components.values()
                   if component.kind in kinds and component.params.get("label", "").upper() == name]
        if len(matches) != 1:
            raise ValueError(f"Need exactly one {'/'.join(kinds)} labelled {name}; found {len(matches)}")
        mapping[name] = matches[0]
    return mapping


def _drive(simulator, inputs, values):
    for name, value in values.items():
        component = inputs[name]
        component.params["value"] = value
        component.params.pop("_bit_values", None)
    simulator.evaluate()
    if simulator.errors: raise ValueError("Circuit simulation error: " + "; ".join(simulator.errors))


def _read(simulator, component):
    values = simulator.inputs.get(component.id, {})
    if component.kind == "OUTPUT": return values.get("A")
    width = component.params.get("width", 4)
    bits = [values.get(f"D{index}") for index in range(width)]
    return None if any(bit is None for bit in bits) else sum(bit << index for index, bit in enumerate(bits))


def _assert_outputs(simulator, outputs, expected, checked):
    for name, value in expected.items():
        actual = _read(simulator, outputs[name])
        checked += 1
        if actual != value:
            shown = "X/disconnected" if actual is None else str(actual)
            raise ValueError(f"Case {checked}: {name} should be {value}, got {shown}. Check its wire, bit order and component configuration.")
    return checked


def _validate_combinational(sim, lesson_id):
    specs = {
        "gates": (("A", "B"), ("Y",),
                  [({"A": a, "B": b}, {"Y": a & b}) for a in (0, 1) for b in (0, 1)]),
        "adders": (("A", "B", "CIN"), ("SUM", "COUT"),
                   [({"A": a, "B": b, "CIN": carry},
                     {"SUM": (a + b + carry) & 1, "COUT": (a + b + carry) >> 1})
                    for a in (0, 1) for b in (0, 1) for carry in (0, 1)]),
        "arithmetic": (("A", "B", "CIN"), ("SUM", "COUT"),
                       [({"A": a, "B": b, "CIN": carry},
                         {"SUM": (a + b + carry) & 15, "COUT": (a + b + carry) >> 4})
                        for a, b, carry in ((0, 0, 0), (3, 5, 0), (15, 1, 0), (15, 15, 1))]),
        "mux_decoder": (("A", "B", "SEL"), ("Y", "D0", "D1", "D2", "D3"),
                        [({"A": a, "B": b, "SEL": select},
                          {"Y": b if select else a,
                           **{f"D{i}": int(i == (a + 2 * b)) for i in range(4)}})
                         for a in (0, 1) for b in (0, 1) for select in (0, 1)]),
        "alu": (("A", "B", "OP"), ("RESULT", "ZERO", "CARRY"),
                [({"A": a, "B": b, "OP": op},
                  {"RESULT": result, "ZERO": int(result == 0), "CARRY": carry})
                 for a, b, op, result, carry in ((5, 3, 0, 8, 0), (255, 1, 0, 0, 1),
                                                 (5, 3, 1, 2, 1), (5, 3, 2, 1, 0),
                                                 (5, 3, 4, 6, 0))]),
    }
    input_names, output_names, cases = specs[lesson_id]
    inputs = _interface(sim.circuit, input_names, ("INPUT", "Bus Input"))
    outputs = _interface(sim.circuit, output_names, ("OUTPUT", "Bus Output"))
    checked = 0
    for drive, expected in cases:
        _drive(sim, inputs, drive)
        checked = _assert_outputs(sim, outputs, expected, checked)
    return checked


def _validate_sequential(sim):
    inputs = _interface(sim.circuit, ("D", "CLK", "DATA"), ("INPUT", "Bus Input"))
    outputs = _interface(sim.circuit, ("Q", "REG"), ("OUTPUT", "Bus Output"))
    checked = 0
    for drive, expected in (({"D": 1, "DATA": 9, "CLK": 0}, {"Q": 0, "REG": 0}),
                            ({"D": 1, "DATA": 9, "CLK": 1}, {"Q": 1, "REG": 9}),
                            ({"D": 0, "DATA": 2, "CLK": 1}, {"Q": 1, "REG": 9}),
                            ({"D": 0, "DATA": 2, "CLK": 0}, {"Q": 1, "REG": 9}),
                            ({"D": 0, "DATA": 2, "CLK": 1}, {"Q": 0, "REG": 2})):
        _drive(sim, inputs, drive)
        sim.step()
        checked = _assert_outputs(sim, outputs, expected, checked)
    return checked


def _validate_ram(sim):
    inputs = _interface(sim.circuit, ("ADDRESS", "DATA", "WE", "CLK"), ("INPUT", "Bus Input"))
    outputs = _interface(sim.circuit, ("Q",), ("OUTPUT", "Bus Output"))
    checked = 0
    for drive, expected in (({"ADDRESS": 3, "DATA": 0xA5, "WE": 1, "CLK": 0}, 0),
                            ({"ADDRESS": 3, "DATA": 0xA5, "WE": 1, "CLK": 1}, 0xA5),
                            ({"ADDRESS": 4, "DATA": 0, "WE": 0, "CLK": 1}, 0),
                            ({"ADDRESS": 3, "DATA": 0, "WE": 0, "CLK": 0}, 0xA5)):
        _drive(sim, inputs, drive)
        sim.step()
        checked = _assert_outputs(sim, outputs, {"Q": expected}, checked)
    return checked


def _validate_cpu(sim, lesson_id):
    candidates = [candidate for candidate in discover_cpus(sim.circuit) if candidate.compatible]
    if not candidates:
        diagnosed = discover_cpus(sim.circuit)
        detail = "; ".join(diagnosed[0].issues[:5]) if diagnosed else "ISA Control Unit is missing"
        raise ValueError("CPU wiring is not ISA 2.1 compatible: " + detail)
    ids = candidates[0].ids
    control = sim.circuit.components[ids["control"]]
    executed = []
    taken_backward = False
    previous = 0
    for _ in range(3000):
        if control.state.get("phase") == "HALT": break
        sim.step()
        count = control.state.get("instructions", 0)
        if count > previous:
            record = control.state["last_completed"]
            executed.append(record["mnemonic"])
            if record["mnemonic"] == "JNZ" and record.get("args") and isinstance(record["args"][0], int):
                target = record["args"][0]
                taken_backward |= (target < record["address"] and
                                   sim.circuit.components[ids["pc"]].state.get("value") == target)
            previous = count
    else: raise ValueError("CPU did not halt within 3000 simulation steps; inspect Clock, PC and branch target")
    if control.state.get("fault"):
        raise ValueError("CPU fault: " + control.state["fault"])
    words = sim.circuit.components[ids["registers"]].state.get("words", {})
    ram = sim.circuit.components[ids["ram"]].state.get("memory", {})
    expected = 9 if lesson_id == "cpu" else 3 if lesson_id == "isa" else 15
    if words.get("0", 0) != expected:
        raise ValueError(f"R0 should be {expected} after execution, got {words.get('0', 0)}")
    if lesson_id == "isa" and (executed.count("JNZ") < 2 or "CMP" not in executed or not taken_backward):
        raise ValueError("Program must actually execute CMP and take a JNZ loop before HLT")
    if lesson_id == "assembly" and (ram.get("32") != 15 or
                                      not {"MOV", "ADD", "STORE", "HLT"}.issubset(executed)):
        raise ValueError("Program must execute MOV, ADD and STORE and leave RAM[0x20]=15")
    if "HLT" not in executed: raise ValueError("Program did not complete HLT")
    return len(executed)


def validate_lesson(circuit, lesson_id):
    if lesson_id not in LESSON_BY_ID: raise ValueError("Unknown lesson")
    try:
        copy = Circuit.from_dict(deepcopy(circuit.to_dict()))
        sim = Simulator(copy)
        if sim.errors: raise ValueError("Circuit error: " + "; ".join(sim.errors))
        sim.reset()  # Every check starts from a clean isolated simulation state.
        if lesson_id in ("gates", "adders", "arithmetic", "mux_decoder", "alu"):
            checked = _validate_combinational(sim, lesson_id)
        elif lesson_id == "sequential": checked = _validate_sequential(sim)
        elif lesson_id == "ram": checked = _validate_ram(sim)
        else: checked = _validate_cpu(sim, lesson_id)
        return LessonResult(True, f"Passed {checked} real simulation checks. {LESSON_BY_ID[lesson_id].completion}", checked)
    except (ValueError, TypeError, KeyError, IndexError) as error:
        return LessonResult(False, str(error), 0)


class TutorialProgress:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else APP_DATA / "tutorial_progress.json"

    def completed(self):
        if not self.path.exists(): return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("completed"), dict):
            raise ValueError("Invalid tutorial progress file")
        return {key: value for key, value in data["completed"].items()
                if (key in LESSON_BY_ID or key in HDL_LESSON_BY_ID or key.startswith("custom:"))
                and isinstance(value, str)}

    def mark(self, lesson_id, result):
        if (lesson_id not in LESSON_BY_ID and lesson_id not in HDL_LESSON_BY_ID
                and not lesson_id.startswith("custom:")) or not result.passed:
            raise ValueError("Only a passed lesson can be recorded")
        completed = self.completed()
        completed[lesson_id] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.path, {"version": 1, "completed": completed})
