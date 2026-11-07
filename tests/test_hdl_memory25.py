"""Limited HDL memory arrays compile to the existing RAM/ROM components."""
from pathlib import Path
import unittest

from engine import Circuit, Simulator
from hdl_model import HDLError, import_verilog, run_vectors
from time_travel_model import SimulationHistory


FOLDER = Path(__file__).resolve().parents[1] / "examples" / "hdl25"


class HDLMemoryTests(unittest.TestCase):
    def test_nested_ram_module_uses_existing_custom_block_simulation(self):
        child = (FOLDER / "ram_module.sv").read_text(encoding="utf-8").replace(
            "module ram_module", "module child")
        top = ("module top(input clk,input we,input [1:0] addr,input [7:0] d,output [7:0] q); "
               "child u(.clk(clk),.we(we),.addr(addr),.d(d),.q(q)); endmodule")
        circuit = import_verilog(child + "\n" + top)
        self.assertIn("child", circuit.blocks)
        rows = run_vectors(child + "\n" + top, [
            {"inputs": {"clk": 0, "we": 0, "addr": 1, "d": 0},
             "expected": {"q": 52}, "step": True},
            {"inputs": {"clk": 1, "we": 1, "addr": 1, "d": 99},
             "expected": {"q": 99}, "step": True}])
        self.assertTrue(all(row["passed"] for row in rows))

    def test_ram_import_write_read_and_round_trip(self):
        source = (FOLDER / "ram_module.sv").read_text(encoding="utf-8")
        circuit = import_verilog(source)
        ram = next(c for c in circuit.components.values() if c.kind == "RAM")
        self.assertEqual(ram.params["init"], {"0": 18, "1": 52})
        self.assertEqual(Circuit.from_dict(circuit.to_dict()).validate(), [])
        rows = run_vectors(source, [
            {"inputs": {"clk": 0, "we": 0, "addr": 1, "d": 0},
             "expected": {"q": 52}, "step": True},
            {"inputs": {"clk": 1, "we": 1, "addr": 1, "d": 90},
             "expected": {"q": 90}, "step": True},
            {"inputs": {"clk": 0, "we": 0, "addr": 1, "d": 0},
             "expected": {"q": 90}, "step": True}])
        self.assertTrue(all(row["passed"] for row in rows))

    def test_rom_import_and_all_contents(self):
        source = (FOLDER / "rom_module.sv").read_text(encoding="utf-8")
        circuit = import_verilog(source)
        self.assertEqual(sum(c.kind == "ROM" for c in circuit.components.values()), 1)
        rows = run_vectors(source, [{"inputs": {"addr": index}, "expected": {"q": 1 << index}}
                                    for index in range(4)])
        self.assertTrue(all(row["passed"] for row in rows))

    def test_ram_state_restores_in_time_travel(self):
        source = (FOLDER / "ram_module.sv").read_text(encoding="utf-8")
        circuit = import_verilog(source)
        sim = Simulator(circuit); history = SimulationHistory(sim)
        ports = {c.params.get("label"): c for c in circuit.components.values() if c.kind == "INPUT"}
        ram = next(c for c in circuit.components.values() if c.kind == "RAM")
        for name, value in (("clk", 1), ("we", 1), ("addr", 1), ("d", 77)):
            ports[name].params["value"] = value
        sim.evaluate(); sim.step(); history.record(sim)
        self.assertEqual(ram.state["memory"]["1"], 77)
        history.navigate(sim, 0)
        self.assertEqual(ram.state.get("memory", ram.params["init"])["1"], 52)

    def test_separate_read_write_addresses_rejected(self):
        source = ("module m(input clk,input we,input [1:0] ra,input [1:0] wa,input [7:0] d,output [7:0] q); "
                  "logic [7:0] mem[0:3]; always_ff @(posedge clk) if(we) mem[wa]<=d; "
                  "assign q=mem[ra]; endmodule")
        with self.assertRaisesRegex(HDLError, "one address port"):
            import_verilog(source)

    def test_unsupported_memory_forms_report_errors(self):
        samples = (
            "module m(input [1:0] a,output [7:0] q); logic [7:0] mem[0:3]; assign q=mem[0]; endmodule",
            "module m(input clk,input [1:0] a,input [7:0] d,output [7:0] q); logic [7:0] mem[0:3]; always_ff @(posedge clk) begin mem[a]<=d; mem[a]<=d; end assign q=mem[a]; endmodule",
            "module m(input [1:0] a,output [7:0] q); logic [7:0] mem[0:3]; initial mem[4]=8'd1; assign q=mem[a]; endmodule",
            "module m(input clk,input [1:0] a,input [7:0] d,output [7:0] q); logic [7:0] mem[0:3]; always_comb mem[a]=d; assign q=mem[a]; endmodule",
        )
        for source in samples:
            with self.subTest(source=source): self.assertRaises(HDLError, import_verilog, source)


if __name__ == "__main__": unittest.main()
