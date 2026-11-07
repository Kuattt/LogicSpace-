"""FPGA packages contain validated, self-contained HDL and constraints."""
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from engine import Circuit
from fpga_model import (PROFILE_FORMAT, blank_workspace, export_fpga_package,
                        load_profile, render_pcf, save_profile, validate_workspace,
                        verify_fpga_package)


SOURCE = "module gate(input a,input b,output y); assign y=a&b; endmodule"


def profile():
    return {"format": PROFILE_FORMAT, "version": 1, "manufacturer": "Unknown",
            "family": "Unknown", "device": "Unknown", "package": "Unknown",
            "source": "User-provided test fixture; no physical device asserted",
            "pins": ["P1", "P2", "P3", "P4"], "clock_pins": ["P1"],
            "constraint_format": "ice40-pcf"}


def workspace():
    data = blank_workspace()
    data.update(name="Gates", top="gate", files={"gate.v": SOURCE}, profile=profile(),
                pins={"a": "P1", "b": "P2", "y": "P3"})
    return data


class FPGATests(unittest.TestCase):
    def test_hdl_ram_package_is_self_contained(self):
        source = (Path(__file__).resolve().parents[1] / "examples" / "hdl25" /
                  "ram_module.sv").read_text(encoding="utf-8")
        data = blank_workspace()
        data["name"] = "RAM array"
        data["top"] = "ram_module"
        data["files"] = {"ram_module.sv": source}
        data["profile"] = profile()
        data["profile"]["pins"] = [f"P{index}" for index in range(1, 22)]
        data["pins"] = {"clk": "P1", "we": "P2"}
        for bit in range(2): data["pins"][f"addr[{bit}]"] = f"P{bit + 3}"
        for bit in range(8):
            data["pins"][f"d[{bit}]"] = f"P{bit + 5}"
            data["pins"][f"q[{bit}]"] = f"P{bit + 13}"
        data["clocks_mhz"] = {"clk": 12.0}
        self.assertTrue(validate_workspace(data).valid, validate_workspace(data).errors)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ram.zip"
            export_fpga_package(data, path)
            self.assertEqual(verify_fpga_package(path)["top"], "ram_module")

    def test_validate_export_verify_and_project_round_trip(self):
        data = workspace()
        self.assertTrue(validate_workspace(data).valid)
        self.assertIn("set_io y P3", render_pcf(data))
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "package.zip"
            export_fpga_package(data, destination)
            result = verify_fpga_package(destination)
            self.assertEqual(result["top"], "gate")
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(archive.read("hdl/gate.v").decode(), SOURCE)
                self.assertIn("set_io a P1", archive.read("constraints/gate.pcf").decode())
            circuit = Circuit(); circuit.fpga_workspace = data
            self.assertEqual(Circuit.from_dict(circuit.to_dict()).fpga_workspace, data)

    def test_profile_round_trip_and_no_invented_pin_defaults(self):
        self.assertIsNone(blank_workspace()["profile"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "device.json"
            save_profile(profile(), path)
            self.assertEqual(load_profile(path), profile())

    def test_reports_multiple_pin_errors_and_clock_constraint(self):
        data = workspace()
        data["pins"] = {"a": "P1", "b": "P1", "absent": "P99"}
        data["clocks_mhz"] = {"y": 12.0}
        errors = "\n".join(validate_workspace(data).errors)
        self.assertIn("Unassigned top-level pin y", errors)
        self.assertIn("both", errors)
        self.assertIn("absent from the profile", errors)
        self.assertIn("not a top-level input", errors)

    def test_known_non_ice40_profile_rejects_ice40_constraints(self):
        data = workspace()
        data["profile"]["manufacturer"] = "Other vendor"
        data["profile"]["family"] = "Other family"
        report = validate_workspace(data)
        self.assertIn("Lattice", "\n".join(report.errors))
        self.assertIn("iCE40 family", "\n".join(report.errors))

    def test_sequential_requires_clock_constraint(self):
        data = workspace()
        data["files"] = {"reg.sv": "module reg1(input clk,input d,output logic q); always_ff @(posedge clk) q<=d; endmodule"}
        data["top"] = "reg1"
        data["pins"] = {"clk": "P1", "d": "P2", "q": "P3"}
        self.assertIn("clock constraint", "\n".join(validate_workspace(data).errors))
        data["clocks_mhz"] = {"clk": 12.0}
        self.assertTrue(validate_workspace(data).valid)
        self.assertIn("set_frequency clk 12", render_pcf(data))

    def test_unsafe_files_and_corrupt_package(self):
        data = workspace()
        data["files"] = {"../escape.v": SOURCE}
        self.assertFalse(validate_workspace(data).valid)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "package.zip"
            export_fpga_package(workspace(), destination)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Duplicate name: 'hdl/gate.v'")
                with zipfile.ZipFile(destination, "a") as archive:
                    archive.writestr("hdl/gate.v", "corrupt")
            with self.assertRaises(ValueError): verify_fpga_package(destination)


if __name__ == "__main__": unittest.main()
