"""Optional external tools must report real availability and bounded results."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from hdl_tools import first_equivalence_mismatch, run_external_vectors
from toolchain_model import detect_tool, run_restricted


class ExternalToolTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "POSIX process-group cancellation")
    def test_cancel_and_timeout_kill_external_process_group(self):
        class FakeProcess:
            pid = 123456
            def poll(self): return None
            def wait(self, timeout): return -9
        with tempfile.TemporaryDirectory() as folder, \
             patch("toolchain_model.shutil.which", return_value="/usr/bin/bwrap"), \
             patch("toolchain_model.subprocess.Popen", return_value=FakeProcess()), \
             patch("toolchain_model.os.killpg") as kill:
            with self.assertRaisesRegex(ValueError, "cancelled"):
                run_restricted(["/usr/bin/true"], folder, cancelled=lambda: True)
            kill.assert_called_with(123456, 9)
            with patch("toolchain_model.time.monotonic", side_effect=[0, 31]):
                with self.assertRaisesRegex(ValueError, "exceeded"):
                    run_restricted(["/usr/bin/true"], folder, timeout=30)
            self.assertEqual(kill.call_count, 2)

    def test_missing_tool_is_reported(self):
        with patch("toolchain_model.shutil.which", return_value=None):
            status = detect_tool("yosys")
            self.assertFalse(status["installed"])
            self.assertFalse(status["available"])
            with tempfile.TemporaryDirectory() as folder:
                reason = "Bubblewrap is required" if os.name == "posix" else "unavailable on Windows"
                with self.assertRaisesRegex(ValueError, reason):
                    run_restricted(["/usr/bin/true"], folder)

    def test_first_mismatch_reports_signal_and_step(self):
        rows = [{"step": 0, "external": {"q": 0}, "logicspace": {"q": 0}},
                {"step": 1, "external": {"q": 1}, "logicspace": {"q": 0}}]
        self.assertEqual(first_equivalence_mismatch(rows),
                         {"step": 1, "signal": "q", "external": 1, "logicspace": 0})
        self.assertIsNone(first_equivalence_mismatch(rows[:1]))

    def test_sequential_testbench_has_aligned_clock_and_nba_observation(self):
        source = "module d(input clk,input d,output logic q); always_ff @(posedge clk) q<=d; endmodule"
        vectors = [{"inputs": {"clk": 0, "d": 1}, "step": True},
                   {"inputs": {"clk": 1, "d": 1}, "step": True}]
        calls = []

        def fake_sandbox(command, folder, timeout=5):
            if "iverilog" in str(command):
                calls.append(Path(folder, "testbench.sv").read_text())
                return ""
            return "LS:0:q:x\nLS:1:q:1\n"

        with patch("hdl_tools.external_availability", return_value=(True, "Available")), \
             patch("hdl_tools.shutil.which", side_effect=lambda name: name), \
             patch("hdl_tools._sandbox", side_effect=fake_sandbox):
            rows = run_external_vectors(source, vectors, "d")
        self.assertTrue(all(row["equivalent"] for row in rows))
        self.assertIn("reg clk = 1'b0;", calls[0])
        self.assertIn("#1; // establish clock baseline", calls[0])
        self.assertIn("#1; // settle combinational logic and nonblocking assignments", calls[0])

    def test_external_comparison_rejects_unaligned_start(self):
        source = "module d(input clk,input d,output logic q); always_ff @(posedge clk) q<=d; endmodule"
        with patch("hdl_tools.external_availability", return_value=(True, "Available")):
            with self.assertRaisesRegex(ValueError, "First vector"):
                run_external_vectors(source, [{"inputs": {"clk": 1, "d": 0}, "step": True}], "d")


if __name__ == "__main__": unittest.main()
