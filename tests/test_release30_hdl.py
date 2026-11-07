"""3.0 sequential HDL checks against the sole LogicSpace Simulator."""
import unittest
from pathlib import Path

from engine import Circuit, Simulator
from hdl_model import HDLError, export_verilog, import_verilog, run_vectors
from time_travel_model import SimulationHistory


class SequentialReleaseTests(unittest.TestCase):
    def test_random_component_ids_do_not_change_async_reset_sampling(self):
        source = ("module d(input clk,input rst,input d,output logic q); "
                  "always_ff @(posedge clk or posedge rst) if(rst) q<=0; else q<=d; endmodule")
        for _ in range(40):
            circuit = import_verilog(source)
            simulator = Simulator(circuit)
            ports = {c.params["label"]: c for c in circuit.components.values() if c.kind == "INPUT"}
            flop = next(c for c in circuit.components.values() if c.kind == "D Flip-Flop")
            ports["d"].params["value"] = 1
            ports["clk"].params["value"] = 1
            simulator.step()
            self.assertEqual(simulator.outputs[flop.id, "Q"], 1)
            ports["rst"].params["value"] = 1
            simulator.evaluate()
            self.assertEqual(simulator.outputs[flop.id, "Q"], 0)

    def test_independent_clock_domains_and_single_edge_commit(self):
        source = ("module pair(input c0,input c1,input d0,input d1,output logic q0,output logic q1); "
                  "always_ff @(posedge c0) q0<=d0; always_ff @(posedge c1) q1<=d1; endmodule")
        circuit = import_verilog(source)
        simulator = Simulator(circuit)
        inputs = {c.params["label"]: c for c in circuit.components.values() if c.kind == "INPUT"}
        outputs = {c.params["label"]: c for c in circuit.components.values() if c.kind == "OUTPUT"}
        inputs["d0"].params["value"] = 1
        inputs["d1"].params["value"] = 1
        inputs["c0"].params["value"] = 1
        simulator.step()
        self.assertEqual(simulator.inputs[outputs["q0"].id]["A"], 1)
        self.assertIsNone(simulator.inputs[outputs["q1"].id]["A"])
        inputs["d0"].params["value"] = 0
        inputs["c1"].params["value"] = 1
        simulator.step()
        self.assertEqual(simulator.inputs[outputs["q0"].id]["A"], 1)
        self.assertEqual(simulator.inputs[outputs["q1"].id]["A"], 1)

    def test_async_reset_priority_and_time_travel(self):
        source = ("module d(input clk,input rst,input d,output logic q); "
                  "always_ff @(posedge clk or posedge rst) if(rst) q<=1'b0; else q<=d; endmodule")
        circuit = import_verilog(source)
        sim = Simulator(circuit)
        history = SimulationHistory(sim)
        inputs = {c.params["label"]: c for c in circuit.components.values() if c.kind == "INPUT"}
        flop = next(c for c in circuit.components.values() if c.kind == "D Flip-Flop")
        inputs["d"].params["value"] = 1
        inputs["clk"].params["value"] = 1
        sim.evaluate(); sim.step(); history.record(sim)
        self.assertEqual(sim.outputs[flop.id, "Q"], 1)
        inputs["rst"].params["value"] = 1
        sim.evaluate(); history.record_mutation(sim)
        self.assertEqual(sim.outputs[flop.id, "Q"], 0)
        self.assertEqual(sim.last_transitions[flop.id]["event"], "asynchronous reset")
        sim.step(); history.record(sim)
        self.assertEqual(sim.outputs[flop.id, "Q"], 0)
        history.navigate(sim, 1, "main")
        self.assertEqual(sim.outputs[flop.id, "Q"], 1)

    def test_active_low_reset_and_export_round_trip(self):
        source = ("module r(input clk,input rst_n,input [7:0] d,output logic [7:0] q); "
                  "always_ff @(posedge clk or negedge rst_n) if(!rst_n) q<=8'd3; else q<=d; endmodule")
        vectors = [
            {"inputs": {"clk": 0, "rst_n": 1, "d": 42}, "expected": {"q": None}, "step": True},
            {"inputs": {"clk": 1, "rst_n": 1, "d": 42}, "expected": {"q": 42}, "step": True},
            {"inputs": {"clk": 1, "rst_n": 0, "d": 42}, "expected": {"q": 3}},
        ]
        self.assertTrue(all(row["passed"] for row in run_vectors(source, vectors)))
        generated = export_verilog(import_verilog(source))
        self.assertIn("negedge rst_n", generated)
        self.assertTrue(all(row["passed"] for row in run_vectors(generated, vectors)))

    def test_partial_vector_writes_preserve_known_bits_and_x(self):
        source = ("module m(input clk,input a,input b,output logic [3:0] q); "
                  "always_ff @(posedge clk) begin q[0]<=a; q[2]<=b; end endmodule")
        circuit = import_verilog(source)
        sim = Simulator(circuit); history = SimulationHistory(sim)
        ports = {c.params["label"]: c for c in circuit.components.values() if c.kind == "INPUT"}
        reg = next(c for c in circuit.components.values() if c.kind == "Register")
        ports["clk"].params["value"] = 1
        ports["a"].params["value"] = 1
        ports["b"].params["value"] = 1
        sim.evaluate(); sim.step(); history.record(sim)
        self.assertEqual([sim.outputs[reg.id, f"Q{i}"] for i in range(4)], [1, None, 1, None])
        self.assertEqual(reg.state["bit_values"], [1, None, 1, None])
        history.navigate(sim, 0)
        self.assertEqual([sim.outputs[reg.id, f"Q{i}"] for i in range(4)], [None] * 4)
        history.navigate(sim, 1)
        self.assertEqual(sim.outputs[reg.id, "Q2"], 1)
        self.assertFalse(Circuit.from_dict(circuit.to_dict()).validate())

    def test_blocking_partial_vector_write(self):
        source = ("module m(input a,input b,output logic [3:0] q); "
                  "always_comb begin q=4'b0000; q[0]=a; q[2]=b; end endmodule")
        self.assertTrue(run_vectors(source, [{"inputs": {"a": 1, "b": 1},
                                              "expected": {"q": 5}}])[0]["passed"])

    def test_shipped_register_export_reimports_with_same_reset_behavior(self):
        source = (Path(__file__).resolve().parents[1] / "examples/hdl25/register8.sv").read_text()
        generated = export_verilog(import_verilog(source))
        vectors = [
            {"inputs": {"clk": 0, "rst": 0, "d": 37}, "expected": {"q": None}, "step": True},
            {"inputs": {"clk": 1, "rst": 0, "d": 37}, "expected": {"q": 37}, "step": True},
            {"inputs": {"clk": 0, "rst": 1, "d": 99}, "expected": {"q": 37}, "step": True},
            {"inputs": {"clk": 1, "rst": 1, "d": 99}, "expected": {"q": 0}, "step": True},
        ]
        self.assertTrue(all(row["passed"] for row in run_vectors(source, vectors)))
        self.assertTrue(all(row["passed"] for row in run_vectors(generated, vectors)))
        self.assertRaises(HDLError, import_verilog,
                          "module m(input [3:0] a,output y); assign y=|a; endmodule")

    def test_unsupported_partial_and_reset_forms_have_diagnostics(self):
        bad = (
            "module m(input a,output logic [3:0] q); always_comb q[0]=a; endmodule",
            "module m(input clk,input d,output logic [3:0] q); always_ff @(posedge clk) q[4]<=d; endmodule",
            "module m(input clk,input r,input d,output logic q); always_ff @(posedge clk or posedge r) q<=d; endmodule",
            "module m(input clk,input r,input d,output logic q); always_ff @(posedge clk or negedge r) if(r) q<=0; else q<=d; endmodule",
        )
        for source in bad:
            with self.subTest(source=source): self.assertRaises(HDLError, import_verilog, source)


if __name__ == "__main__": unittest.main()
