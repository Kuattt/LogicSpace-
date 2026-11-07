"""Assembly programs run through the wired LogicSpace PC/ROM/IR/CU/ALU/RF/RAM."""
import json
import unittest
from pathlib import Path

from cpu_board import create_cpu_circuit, load_program, validate_board, program_matches_rom
from cpu_debugger import CpuBreakpointManager, CpuStepper
from cpu_isa import AssemblyError, BY_OPCODE, assemble, decode
from engine import Circuit, Simulator
from testbench_model import TestbenchSession, new_testbench, signal_ref_dict
from timing_model import SignalRef
from time_travel_model import SimulationHistory
from tracing_model import TraceAnalyzer, TraceFrame


def execute(source, limit=3000):
    circuit = create_cpu_circuit(source)
    simulator = Simulator(circuit)
    ids = circuit.cpu_workspace["ids"]
    controller = circuit.components[ids["control"]]
    for _ in range(limit):
        if controller.state.get("phase") == "HALT": break
        simulator.step()
    else: raise AssertionError("CPU did not stop within the test limit")
    return circuit, simulator, ids


def words(circuit, ids):
    return circuit.components[ids["registers"]].state.get("words", {})


class AssemblerTests(unittest.TestCase):
    def test_exact_bytes_labels_constants_org_and_exports(self):
        source = ".EQU DATA, 0x20\nSTART: MOV R0, 10\nMOV R1, 5\nADD R0, R1\nSTORE R0, DATA\nHLT\n.ORG 0x20\n.BYTE 0xA5\n.WORD START + 1\n"
        result = assemble(source)
        self.assertEqual(result.image[:13], bytes.fromhex("10 00 0A 10 01 05 20 00 01 13 00 20 01"))
        self.assertEqual(result.image[0x20:0x23], bytes((0xA5, 1, 0)))
        self.assertEqual(result.symbols["DATA"], 0x20)
        self.assertEqual(result.address_to_line[6], 4)
        self.assertEqual(decode(result.image, 0), "MOV R0, 0x0A")
        self.assertEqual(result, assemble(source))
        self.assertTrue(result.intel_hex().endswith(":00000001FF\n"))
        self.assertIn("STORE R0, DATA", result.listing_text())
        for line in result.intel_hex().strip().splitlines():
            data = bytes.fromhex(line[1:])
            self.assertEqual(sum(data) & 0xFF, 0)

    def test_every_opcode_has_unique_documented_format(self):
        self.assertEqual(len(BY_OPCODE), 24)
        self.assertEqual(len({instruction.opcode for instruction in BY_OPCODE.values()}), 24)
        self.assertEqual({instruction.mnemonic for instruction in BY_OPCODE.values()},
                         {"MOV", "LOAD", "STORE", "ADD", "SUB", "AND", "OR", "XOR", "NOT",
                          "SHL", "SHR", "CMP", "JMP", "JZ", "JNZ", "JC", "JNC", "CALL",
                          "RET", "PUSH", "POP", "HLT", "NOP"})

    def test_errors_are_line_numbered_and_safe(self):
        for source, message in (("BAD R0\n", "unknown instruction"),
                                ("MOV R4, 1\n", "invalid register"),
                                ("MOV R0, 256\n", "8 bits"),
                                ("JMP MISSING\n", "undefined symbol"),
                                (".ORG 255\nMOV R0, 1\n", "exceeds"),
                                (".ORG 0\nNOP\n.ORG 0\nHLT\n", "already used"),
                                (".EQU A, B\n.EQU B, A\nNOP\n", "circular")):
            with self.subTest(source=source), self.assertRaisesRegex(AssemblyError, message):
                assemble(source)
        with self.assertRaises(AssemblyError) as context:
            assemble("NOP\nJMP MISSING")
        self.assertEqual(context.exception.line, 2)


class WiredExecutionTests(unittest.TestCase):
    def test_mov_register_and_immediate_nop_hlt(self):
        circuit, simulator, ids = execute("NOP\nMOV R0, 42\nMOV R1, R0\nHLT\n")
        self.assertEqual((words(circuit, ids)["0"], words(circuit, ids)["1"]), (42, 42))
        self.assertEqual(circuit.components[ids["control"]].state["instructions"], 4)
        self.assertEqual(circuit.components[ids["ir"]].state["value"], 1)
        self.assertFalse(simulator.errors)

    def test_each_alu_instruction_uses_the_wired_alu(self):
        expected = {"ADD": (8, 0), "SUB": (2, 1), "AND": (1, 0), "OR": (7, 0),
                    "XOR": (6, 0), "NOT": (250, 0), "SHL": (10, 0), "SHR": (2, 1),
                    "CMP": (5, 1)}
        for name, (value, carry) in expected.items():
            with self.subTest(instruction=name):
                operand = "" if name in ("NOT", "SHL", "SHR") else ", R1"
                circuit, _, ids = execute(f"MOV R0, 5\nMOV R1, 3\n{name} R0{operand}\nHLT\n")
                self.assertEqual(words(circuit, ids)["0"], value)
                self.assertEqual(circuit.components[ids["control"]].state["carry"], carry)

    def test_store_load_memory_and_stack(self):
        source = "MOV R0, 42\nSTORE R0, 0x20\nMOV R0, 0\nLOAD R0, 0x20\nPUSH R0\nMOV R0, 1\nPOP R0\nHLT\n"
        circuit, _, ids = execute(source)
        self.assertEqual(words(circuit, ids)["0"], 42)
        self.assertEqual(circuit.components[ids["ram"]].state["memory"], {"32": 42, "255": 42})
        self.assertEqual(circuit.components[ids["control"]].state.get("sp", 255), 255)

    def test_conditional_branches_and_jump(self):
        scenarios = (("JZ", 1, 1, True), ("JZ", 1, 2, False),
                     ("JNZ", 1, 2, True), ("JNZ", 1, 1, False),
                     ("JC", 2, 1, True), ("JC", 1, 2, False),
                     ("JNC", 1, 2, True), ("JNC", 2, 1, False))
        for name, left, right, taken in scenarios:
            with self.subTest(name=name, left=left, right=right):
                source = (f"MOV R0, {left}\nMOV R1, {right}\nCMP R0, R1\n"
                          f"{name} TARGET\nMOV R2, 99\nTARGET: HLT\n")
                circuit, _, ids = execute(source)
                self.assertEqual("2" not in words(circuit, ids), taken)
        circuit, _, ids = execute("JMP TARGET\nMOV R0, 99\nTARGET: HLT\n")
        self.assertNotIn("0", words(circuit, ids))

    def test_call_ret_and_step_over_out(self):
        source = "CALL SUB\nHLT\nSUB: MOV R0, 7\nRET\n"
        circuit = create_cpu_circuit(source)
        simulator = Simulator(circuit)
        runner = CpuStepper(simulator)
        self.assertTrue(runner.step_instruction())
        self.assertEqual(runner.state["call_depth"], 1)
        self.assertTrue(runner.step_out())
        self.assertEqual(runner.state["call_depth"], 0)
        self.assertEqual(words(circuit, circuit.cpu_workspace["ids"])["0"], 7)
        self.assertTrue(runner.step_instruction())
        self.assertEqual(runner.state["phase"], "HALT")
        halted_tick = circuit.tick
        self.assertFalse(runner.step_instruction())
        self.assertEqual(circuit.tick, halted_tick)
        self.assertEqual(circuit.components[circuit.cpu_workspace["ids"]["ram"]].state["memory"]["255"], 2)
        second = create_cpu_circuit(source)
        over = CpuStepper(Simulator(second))
        self.assertTrue(over.step_over())
        self.assertEqual(over.state["call_depth"], 0)
        self.assertEqual(over.state["instructions"], 3)  # CALL, MOV in subroutine, RET

    def test_clock_cycle_is_distinct_from_instruction(self):
        circuit = create_cpu_circuit("MOV R0, 3\nHLT\n")
        runner = CpuStepper(Simulator(circuit))
        self.assertTrue(runner.step_clock_cycle())
        self.assertEqual(runner.state["phase"], "DECODE")
        self.assertEqual(runner.state.get("instructions", 0), 0)
        self.assertTrue(runner.step_instruction())
        self.assertEqual(runner.state["instructions"], 1)
        self.assertEqual(words(circuit, circuit.cpu_workspace["ids"])["0"], 3)

    def test_invalid_opcode_and_stack_underflow(self):
        circuit, _, ids = execute("RET\n")
        self.assertIn("Stack underflow", circuit.components[ids["control"]].state["fault"])
        circuit = create_cpu_circuit("NOP\n")
        ids = circuit.cpu_workspace["ids"]
        circuit.components[ids["rom"]].params["contents"]["0"] = 0xFF
        simulator = Simulator(circuit)
        for _ in range(20):
            simulator.step()
            if circuit.components[ids["control"]].state.get("phase") == "HALT": break
        self.assertIn("Invalid opcode", circuit.components[ids["control"]].state["fault"])
        circuit, _, ids = execute("MOV R0, 1\n" + "PUSH R0\n" * 65 + "HLT\n")
        control = circuit.components[ids["control"]].state
        self.assertIn("Stack overflow", control["fault"])
        self.assertEqual(control["sp"], 0xBF)
        self.assertEqual(len(circuit.components[ids["ram"]].state["memory"]), 64)

    def test_time_travel_and_program_loading_project_independence(self):
        circuit = create_cpu_circuit("MOV R0, 5\nHLT\n")
        simulator = Simulator(circuit)
        history = SimulationHistory(simulator)
        runner = CpuStepper(simulator)
        runner.step_instruction()
        history.record(simulator)
        first_step = circuit.tick
        self.assertEqual(words(circuit, circuit.cpu_workspace["ids"])["0"], 5)
        history.navigate(simulator, 0)
        self.assertEqual(words(circuit, circuit.cpu_workspace["ids"]), {})
        runner.step_instruction()
        self.assertEqual(circuit.tick, first_step)
        self.assertEqual(words(circuit, circuit.cpu_workspace["ids"])["0"], 5)
        reopened = Circuit.from_dict(json.loads(json.dumps(circuit.to_dict())))
        self.assertEqual(reopened.cpu_workspace["source"], "MOV R0, 5\nHLT\n")
        program = load_program(reopened, "MOV R0, 9\nHLT\n")
        self.assertEqual(program.image[:3], bytes((0x10, 0, 9)))
        self.assertEqual(circuit.cpu_workspace["source"], "MOV R0, 5\nHLT\n")

    def test_cpu_time_travel_branch_restores_microphase_and_memory(self):
        circuit = create_cpu_circuit("MOV R0, 7\nSTORE R0, 0x20\nHLT\n")
        simulator = Simulator(circuit)
        history = SimulationHistory(simulator)
        ids = circuit.cpu_workspace["ids"]
        for _ in range(20):
            simulator.step(); history.record(simulator)
        self.assertEqual(circuit.components[ids["ram"]].state["memory"]["32"], 7)
        previous_branch = history.active_branch
        history.navigate(simulator, 10)
        self.assertEqual(circuit.components[ids["control"]].state["phase"], "FETCH")
        self.assertNotIn("32", circuit.components[ids["ram"]].state.get("memory", {}))
        for _ in range(10):
            simulator.step(); history.record(simulator)
        self.assertNotEqual(history.active_branch, previous_branch)
        self.assertEqual(circuit.components[ids["ram"]].state["memory"]["32"], 7)
        self.assertEqual(history.snapshot_at(previous_branch, 20).states[ids["ram"]]["memory"]["32"], 7)

    def test_cpu_program_in_existing_isolated_testbench(self):
        circuit = create_cpu_circuit("MOV R0, 5\nHLT\n")
        ids = circuit.cpu_workspace["ids"]
        bench = new_testbench("CPU instruction")
        bench["signals"] = [{"id": "r0", "role": "observe",
                             "ref": signal_ref_dict(SignalRef.bus_port(ids["registers"], "R0", "output"))}]
        bench["steps"] = [{"drive": {}, "expect": {}, "repeat": 1} for _ in range(11)]
        bench["steps"][10]["expect"] = {"r0": 5}
        before = circuit.to_dict()
        result = TestbenchSession(circuit, bench).run()
        self.assertEqual((result.passed, result.failed), (1, 0))
        self.assertEqual(circuit.to_dict(), before)

    def test_isa_control_trace_uses_recorded_microphase(self):
        circuit = create_cpu_circuit("MOV R0, 5\nHLT\n")
        simulator = Simulator(circuit)
        runner = CpuStepper(simulator)
        runner.step_instruction()
        control_id = circuit.cpu_workspace["ids"]["control"]
        analyzer = TraceAnalyzer(circuit, TraceFrame.from_simulator(simulator), simulator)
        explanation = " ".join(analyzer.explain(SignalRef.component_pin(control_id, "RF_WE", "output")))
        self.assertIn("microphase EXEC→FETCH", explanation)
        self.assertIn("MOV at address 0x00 completed", explanation)
        self.assertIn("clock edge", explanation)

    def test_missing_physical_connection_is_rejected(self):
        circuit = create_cpu_circuit("MOV R0, 5\nHLT\n")
        ids = circuit.cpu_workspace["ids"]
        victim = next(wid for wid, wire in circuit.wires.items()
                      if wire.source == ids["alu"] and wire.target == ids["rf_imm"])
        circuit.wires.pop(victim)
        with self.assertRaisesRegex(ValueError, "physical connection"):
            validate_board(circuit)

    def test_cpu_breakpoints_for_line_address_register_memory(self):
        source = "MOV R0, 5\nSTORE R0, 0x20\nHLT\n"
        circuit = create_cpu_circuit(source)
        simulator = Simulator(circuit)
        manager = CpuBreakpointManager(); manager.bind(circuit)
        manager.add("line", 1)
        manager.add("address", 0)
        manager.add("register", 0, 5)
        manager.add("memory", 0x20, "write")
        hits = []
        for _ in range(100):
            simulator.step()
            hits.extend(manager.check(simulator))
            if circuit.components[circuit.cpu_workspace["ids"]["control"]].state.get("phase") == "HALT": break
        kinds = {event.reason for event in hits}
        self.assertEqual(kinds, {"line", "address", "register", "memory"})
        self.assertTrue(any(event.line == 1 and event.address == 0 for event in hits))

    def test_line_mapping_disables_if_rom_is_edited_outside_assembler(self):
        circuit = create_cpu_circuit("MOV R0, 5\nHLT\n")
        manager = CpuBreakpointManager(); manager.bind(circuit)
        self.assertTrue(manager.source_sync)
        circuit.components[circuit.cpu_workspace["ids"]["rom"]].params["contents"]["0"] = 0
        self.assertFalse(program_matches_rom(circuit, manager.program))
        simulator = Simulator(circuit)
        manager.add("line", 1)
        manager.add("address", 0)
        hits = []
        for _ in range(10):
            simulator.step(); hits.extend(manager.check(simulator))
        self.assertFalse(manager.source_sync)
        self.assertFalse(any(event.reason == "line" for event in hits))
        self.assertTrue(any(event.reason == "address" for event in hits))

    def test_shipped_assembly_projects_execute_expected_results(self):
        folder = Path(__file__).resolve().parents[1] / "examples" / "assembly"
        expected = {"arithmetic": (10, None), "loop": (5, None),
                    "memory": (42, 42), "fibonacci": (21, None),
                    "stack": (14, None)}
        for name, (register0, ram32) in expected.items():
            with self.subTest(program=name):
                source = (folder / f"{name}.asm").read_text(encoding="utf-8")
                program = assemble(source)
                self.assertEqual((folder / f"{name}.bin").read_bytes(), program.image)
                self.assertEqual((folder / f"{name}.hex").read_text(encoding="ascii"), program.intel_hex())
                circuit = Circuit.load(folder / f"{name}.json")
                ids = validate_board(circuit)
                self.assertEqual(circuit.cpu_workspace["source"], source)
                simulator = Simulator(circuit)
                control = circuit.components[ids["control"]]
                for _ in range(3000):
                    if control.state.get("phase") == "HALT": break
                    simulator.step()
                self.assertEqual(control.state.get("phase"), "HALT")
                self.assertIsNone(control.state.get("fault"))
                self.assertEqual(words(circuit, ids)["0"], register0)
                if ram32 is not None:
                    self.assertEqual(circuit.components[ids["ram"]].state["memory"]["32"], ram32)
                if name == "fibonacci": self.assertEqual(words(circuit, ids)["1"], 34)
                if name == "stack":
                    self.assertEqual(words(circuit, ids)["2"], 7)
                    self.assertEqual(control.state.get("sp", 255), 255)


if __name__ == "__main__":
    unittest.main()
