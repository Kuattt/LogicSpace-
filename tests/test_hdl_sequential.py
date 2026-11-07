"""Sequential HDL is compiled to editable components and the real Simulator."""
import unittest
from pathlib import Path

from engine import BusWire, Circuit, Simulator
from hdl_model import diagnose_hdl, export_verilog, import_verilog, run_vectors
from time_travel_model import SimulationHistory


class SequentialHDLTests(unittest.TestCase):
    def test_canvas_import_can_use_real_clock_generator(self):
        source = "module d(input clk,input d,output logic q); always_ff @(posedge clk) q<=d; endmodule"
        circuit = import_verilog(source, clock_generators=True)
        clock = next(c for c in circuit.components.values() if c.kind == "Clock Generator")
        flip = next(c for c in circuit.components.values() if c.kind == "D Flip-Flop")
        self.assertTrue(any(w.source == clock.id and w.target == flip.id and w.target_pin == "CLK"
                            for w in circuit.wires.values()))
        data = next(c for c in circuit.components.values() if c.kind == "INPUT")
        data.params["value"] = 1
        sim = Simulator(circuit)
        self.assertFalse(sim.errors)
        sim.step(); self.assertIsNone(sim.outputs[flip.id, "Q"])
        sim.step(); self.assertEqual(sim.outputs[flip.id, "Q"], 1)
        exported = export_verilog(circuit)
        self.assertIn("input clk", exported)
        self.assertIn("always @(posedge clk)", exported)

    def test_two_clock_domains_update_only_on_their_edges(self):
        source = ("module dual(input c0,input c1,input d0,input d1,output logic q0,output logic q1); "
                  "always_ff @(posedge c0) q0<=d0; always_ff @(posedge c1) q1<=d1; endmodule")
        rows = run_vectors(source, [
            {"inputs": {"c0": 0, "c1": 0, "d0": 1, "d1": 1},
             "expected": {"q0": None, "q1": None}, "step": True},
            {"inputs": {"c0": 1, "c1": 0, "d0": 1, "d1": 1},
             "expected": {"q0": 1, "q1": None}, "step": True},
            {"inputs": {"c0": 0, "c1": 1, "d0": 0, "d1": 1},
             "expected": {"q0": 1, "q1": 1}, "step": True},
            {"inputs": {"c0": 1, "c1": 0, "d0": 0, "d1": 0},
             "expected": {"q0": 0, "q1": 1}, "step": True}])
        self.assertTrue(all(row["passed"] for row in rows))

    def test_all_shipped_sequential_examples_import_and_simulate(self):
        folder = Path(__file__).resolve().parents[1] / "examples" / "hdl25"
        for path in folder.glob("*.sv"):
            with self.subTest(path=path.name):
                circuit = import_verilog(path.read_text(encoding="utf-8"))
                self.assertFalse(circuit.validate())
                self.assertFalse(Simulator(circuit).errors)
        shift = (folder / "shift_register.sv").read_text(encoding="utf-8")
        rows = run_vectors(shift, [
            {"inputs": {"clk": 0, "d": 1}, "expected": {"q0": None}, "step": True},
            {"inputs": {"clk": 1, "d": 1}, "expected": {"q0": 1, "q1": None}, "step": True},
            {"inputs": {"clk": 0, "d": 0}, "expected": {"q0": 1}, "step": True},
            {"inputs": {"clk": 1, "d": 0}, "expected": {"q0": 0, "q1": 1}, "step": True}])
        self.assertTrue(all(row["passed"] for row in rows))
        fsm = (folder / "simple_fsm.sv").read_text(encoding="utf-8")
        rows = run_vectors(fsm, [
            {"inputs": {"clk": 0, "reset": 1, "start": 0}, "expected": {"done": None}, "step": True},
            {"inputs": {"clk": 1, "reset": 1, "start": 0}, "expected": {"done": 0}, "step": True},
            {"inputs": {"clk": 0, "reset": 0, "start": 1}, "expected": {"done": 0}, "step": True},
            {"inputs": {"clk": 1, "reset": 0, "start": 1}, "expected": {"done": 1}, "step": True},
            {"inputs": {"clk": 0, "reset": 0, "start": 0}, "expected": {"done": 1}, "step": True},
            {"inputs": {"clk": 1, "reset": 0, "start": 0}, "expected": {"done": 0}, "step": True}])
        self.assertTrue(all(row["passed"] for row in rows))
    def test_rising_dff_and_unknown_initial_state(self):
        source = "module d(input clk,input d,output logic q); always_ff @(posedge clk) q <= d; endmodule"
        circuit = import_verilog(source)
        self.assertEqual(sum(c.kind == "D Flip-Flop" for c in circuit.components.values()), 1)
        cases = [({"clk": 0, "d": 1}, None), ({"clk": 1, "d": 1}, 1),
                 ({"clk": 1, "d": 0}, 1), ({"clk": 0, "d": 0}, 1),
                 ({"clk": 1, "d": 0}, 0)]
        self.assertTrue(all(row["passed"] for row in run_vectors(source, [
            {"inputs": drive, "expected": {"q": expected}, "step": True} for drive, expected in cases])))
        self.assertIn("always @(posedge", export_verilog(circuit))

    def test_falling_edge(self):
        source = "module d(input clk,input d,output logic q); always @(negedge clk) q <= d; endmodule"
        result = run_vectors(source, [
            {"inputs": {"clk": 1, "d": 0}, "expected": {"q": None}, "step": True},
            {"inputs": {"clk": 0, "d": 1}, "expected": {"q": 1}, "step": True}])
        self.assertTrue(all(row["passed"] for row in result))
        self.assertIn("always @(negedge", export_verilog(import_verilog(source)))

    def test_register_sync_reset_and_bus(self):
        source = ("module r(input clk,input rst,input [7:0] d,output logic [7:0] q); "
                  "always_ff @(posedge clk) begin if(rst) q <= 8'd0; else q <= d; end endmodule")
        circuit = import_verilog(source)
        self.assertIn("Register", {c.kind for c in circuit.components.values()})
        self.assertTrue(any(isinstance(w, BusWire) for w in circuit.wires.values()))
        rows = run_vectors(source, [
            {"inputs": {"clk": 0, "rst": 1, "d": 7}, "expected": {"q": None}, "step": True},
            {"inputs": {"clk": 1, "rst": 1, "d": 7}, "expected": {"q": 0}, "step": True},
            {"inputs": {"clk": 0, "rst": 0, "d": 9}, "expected": {"q": 0}, "step": True},
            {"inputs": {"clk": 1, "rst": 0, "d": 9}, "expected": {"q": 9}, "step": True}])
        self.assertTrue(all(row["passed"] for row in rows))
        self.assertEqual(Circuit.from_dict(circuit.to_dict()).validate(), [])

    def test_counter_feedback(self):
        source = ("module c(input clk,input rst,output logic [7:0] q); "
                  "always_ff @(posedge clk) if(rst) q<=8'd0; else q<=q+8'd1; endmodule")
        values = ((0, 1, None), (1, 1, 0), (0, 0, 0), (1, 0, 1),
                  (0, 0, 1), (1, 0, 2))
        self.assertTrue(all(row["passed"] for row in run_vectors(source, [
            {"inputs": {"clk": clk, "rst": rst}, "expected": {"q": q}, "step": True}
            for clk, rst, q in values])))

    def test_two_registers_commit_from_same_pre_edge_state(self):
        source = ("module swap(input clk,input a, input b,output logic q0,output logic q1); "
                  "always_ff @(posedge clk) begin q0 <= q1; q1 <= a; end endmodule")
        rows = run_vectors(source, [
            {"inputs": {"clk": 0, "a": 1, "b": 0}, "expected": {"q0": None, "q1": None}, "step": True},
            {"inputs": {"clk": 1, "a": 1, "b": 0}, "expected": {"q0": None, "q1": 1}, "step": True},
            {"inputs": {"clk": 0, "a": 0, "b": 0}, "expected": {"q0": None, "q1": 1}, "step": True},
            {"inputs": {"clk": 1, "a": 0, "b": 0}, "expected": {"q0": 1, "q1": 0}, "step": True}])
        self.assertTrue(all(row["passed"] for row in rows))

    def test_comb_if_and_case_use_verilog_x_branch_semantics(self):
        conditional = "module m(input a,input b,output logic y); always_comb if(a) y=b; else y=0; endmodule"
        self.assertTrue(run_vectors(conditional, [{"inputs": {"a": None, "b": 1},
                                                   "expected": {"y": 0}}])[0]["passed"])
        case = ("module m(input [1:0] s,input a,input b,output logic y); "
                "always_comb case(s) 2'd0:y=a; 2'd1:y=b; default:y=1'b0; endcase endmodule")
        self.assertTrue(run_vectors(case, [{"inputs": {"s": None, "a": 1, "b": 1},
                                            "expected": {"y": 0}}])[0]["passed"])

    def test_blocking_comb_and_missing_assignment_diagnostic(self):
        source = "module m(input a,input b,output logic y); always_comb begin y=0; if(a) y=b; end endmodule"
        self.assertTrue(run_vectors(source, [{"inputs": {"a": 1, "b": 1},
                                              "expected": {"y": 1}}])[0]["passed"])
        bad = "module m(input a,input b,output logic y); always_comb if(a) y=b; endmodule"
        diagnostics = diagnose_hdl(bad, filename="bad.sv")
        self.assertEqual(diagnostics[0].category, "latch-inference")
        self.assertEqual(diagnostics[0].file, "bad.sv")
        self.assertIn("every branch", diagnostics[0].fix)

    def test_invalid_procedural_forms(self):
        samples = (
            "module m(input clk,input d,output logic q); always @(clk) q<=d; endmodule",
            "module m(input clk,input d,output logic q); always_ff @(posedge clk) q=d; endmodule",
            "module m(input d,output logic q); always_comb q<=d; endmodule",
            "module m(input a,output logic q); assign q=a; always_comb q=a; endmodule",
        )
        for source in samples:
            with self.subTest(source=source): self.assertTrue(diagnose_hdl(source))

    def test_time_travel_restores_imported_state(self):
        source = "module d(input clk,input d,output logic q); always_ff @(posedge clk) q<=d; endmodule"
        circuit = import_verilog(source)
        sim = Simulator(circuit)
        history = SimulationHistory(sim)
        inputs = {c.params.get("label"): c for c in circuit.components.values() if c.kind == "INPUT"}
        flip = next(c for c in circuit.components.values() if c.kind == "D Flip-Flop")
        inputs["d"].params["value"] = 1
        inputs["clk"].params["value"] = 1
        sim.evaluate(); sim.step(); history.record(sim)
        self.assertEqual(flip.state["q"], 1)
        history.navigate(sim, 0)
        self.assertIsNone(sim.outputs[flip.id, "Q"])
        self.assertEqual(circuit.tick, 0)


if __name__ == "__main__": unittest.main()
