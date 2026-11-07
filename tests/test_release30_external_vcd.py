"""External waveform export is gated on a real process output file."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hdl_tools import run_external_vectors


SOURCE = "module gate(input a,input b,output y); assign y=a&b; endmodule"
VECTORS = [{"inputs": {"a": 0, "b": 1}, "expected": {"y": 0}},
           {"inputs": {"a": 1, "b": 1}, "expected": {"y": 1}}]


class ExternalVcdTests(unittest.TestCase):
    def test_vcd_is_exported_only_after_tool_generates_it(self):
        commands = []
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "measured.vcd"
            def fake_process(command, workdir):
                commands.append(command)
                if command[0] == "/fake/vvp":
                    (Path(workdir) / "wave.vcd").write_text(
                        "$date test $end\n$enddefinitions $end\n#0\n0!\n#1\n1!\n", encoding="ascii")
                    return "LS:0:y:0\nLS:1:y:1\n"
                self.assertIn('$dumpfile("wave.vcd")',
                              (Path(workdir) / "testbench.sv").read_text(encoding="utf-8"))
                return ""
            with patch("hdl_tools.external_availability", return_value=(True, "Available")), \
                 patch("hdl_tools.shutil.which", side_effect=lambda name: "/fake/" + name), \
                 patch("hdl_tools._sandbox", side_effect=fake_process):
                rows = run_external_vectors(SOURCE, VECTORS, vcd_path=destination)
            self.assertTrue(all(row["equivalent"] for row in rows))
            self.assertIn("$enddefinitions", destination.read_text(encoding="ascii"))
            self.assertEqual(len(commands), 2)

    def test_missing_vcd_is_reported_without_creating_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "missing.vcd"
            with patch("hdl_tools.external_availability", return_value=(True, "Available")), \
                 patch("hdl_tools.shutil.which", side_effect=lambda name: "/fake/" + name), \
                 patch("hdl_tools._sandbox", return_value="LS:0:y:0\n"):
                self.assertRaisesRegex(ValueError, "did not produce", run_external_vectors,
                                       SOURCE, VECTORS[:1], vcd_path=destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__": unittest.main()
