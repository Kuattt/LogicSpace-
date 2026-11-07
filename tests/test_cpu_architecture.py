"""Universal CPU discovery, binding and execution through the shared engine."""
import json
import unittest

from cpu_architecture import (REQUIRED_LINKS, ROLES, bind_cpu, discover_cpus,
                              export_profile, get_active_binding, get_bindings,
                              match_profile, rebind_cpu, select_cpu, sync_active_from_clocks, unbind_cpu,
                              validate_mapping)
from cpu_board import (create_cpu_circuit, load_program, load_rom_image,
                       parse_intel_hex, program_matches_rom, validate_board)
from cpu_debugger import CpuBreakpointManager, CpuStepper
from cpu_isa import assemble
from engine import Circuit, Simulator, copy_selection
from time_travel_model import SimulationHistory


def manually_wired_cpu(circuit, source, x=0):
    """Construct every component and link with the public editor model API."""
    program = assemble(source)
    params = {
        "clock": {"period": 2}, "enable": {"value": 1}, "reset": {"value": 0},
        "pc": {"width": 8}, "ir": {"width": 8},
        "rom": {"address_bits": 8, "data_bits": 8, "depth": 256,
                "contents": {str(a): program.image[a] for a in program.used_addresses}},
        "ram": {"address_bits": 8, "data_bits": 8, "depth": 256},
        "registers": {"registers": 4, "data_bits": 8, "read_ports": 2},
        "alu": {"width": 8, "alu_version": 2},
        **{role: {"width": 8} for role in ("rf_imm", "rf_mem", "rf_reg", "pc_data", "mem_data")},
    }
    ids = {}
    for index, (role, kind) in enumerate(ROLES.items()):
        component = circuit.add(kind, x + (index % 5) * 280,
                                (index // 5) * 320, params.get(role, {}))
        ids[role] = component.id
    for source_role, output, target_role, input_pin, width in REQUIRED_LINKS:
        if width == 1:
            circuit.connect(ids[source_role], output, ids[target_role], input_pin)
        else:
            circuit.connect_bus(ids[source_role], output, ids[target_role], input_pin)
    return ids


class DiscoveryTests(unittest.TestCase):
    def test_reference_and_manual_board_are_discovered_without_manifest(self):
        for circuit in (create_cpu_circuit("HLT\n"), Circuit()):
            if not circuit.components: manually_wired_cpu(circuit, "HLT\n")
            candidate, = discover_cpus(circuit)
            self.assertTrue(candidate.compatible, candidate.issues)
            self.assertEqual(len(candidate.ids), len(ROLES))
            self.assertEqual(candidate.profile["isa_version"], "2.1")
            self.assertEqual(validate_mapping(circuit, candidate.ids), [])

    def test_missing_links_and_width_issues_are_aggregated(self):
        circuit = Circuit(); ids = manually_wired_cpu(circuit, "HLT\n")
        for source, target in (("clock", "pc"), ("control", "alu"), ("control", "registers")):
            wid = next(wid for wid, wire in circuit.wires.items()
                       if wire.source == ids[source] and wire.target == ids[target])
            circuit.wires.pop(wid)
        circuit.components[ids["rom"]].params["data_bits"] = 4
        candidate, = discover_cpus(circuit)
        self.assertFalse(candidate.compatible)
        report = "\n".join(candidate.issues)
        self.assertIn("clock.Q → pc.CLK", report)
        self.assertIn("ALU_OP", report)
        self.assertIn("8 data bits", report)
        self.assertGreaterEqual(len(candidate.issues), 4)

    def test_component_names_do_not_establish_compatibility(self):
        circuit = Circuit()
        for role, kind in ROLES.items(): circuit.add(kind, params={"label": role})
        candidate, = discover_cpus(circuit)
        self.assertFalse(candidate.compatible)
        self.assertGreater(len(candidate.issues), 10)

    def test_missing_component_and_stale_legacy_metadata_do_not_block_project_open(self):
        circuit = create_cpu_circuit("HLT\n")
        circuit.remove(circuit.cpu_workspace["ids"]["alu"])
        reopened = Circuit.from_dict(json.loads(json.dumps(circuit.to_dict())))
        self.assertEqual(len(discover_cpus(reopened)), 1)
        with self.assertRaisesRegex(ValueError, "alu"):
            validate_board(reopened)

    def test_unrelated_invalid_wire_does_not_invalidate_cpu(self):
        circuit = Circuit(); manually_wired_cpu(circuit, "HLT\n")
        source = circuit.add("Bus Input", params={"width": 4})
        target = circuit.add("Bus Output", params={"width": 4})
        circuit.connect_bus(source.id, "Q", target.id, "D")
        target.params["width"] = 8
        self.assertTrue(circuit.validate())
        self.assertTrue(discover_cpus(circuit)[0].compatible)


class BindingTests(unittest.TestCase):
    def test_manual_bind_assembly_execution_and_unbind(self):
        source = "MOV R0, 9\nHLT\n"
        circuit = Circuit(); manually_wired_cpu(circuit, source)
        candidate, = discover_cpus(circuit)
        binding = bind_cpu(circuit, candidate, "Hand wired", source)
        self.assertEqual(validate_board(circuit), binding["ids"])
        simulator = Simulator(circuit)
        runner = CpuStepper(simulator, binding=binding)
        runner.step_instruction()
        self.assertEqual(circuit.components[binding["ids"]["registers"]].state["words"]["0"], 9)
        unbind_cpu(circuit)
        self.assertIsNone(get_active_binding(circuit))
        self.assertEqual(len(discover_cpus(circuit)), 1)
        rebound = bind_cpu(circuit, discover_cpus(circuit)[0], source=source)
        self.assertEqual(rebound["ids"], binding["ids"])

    def test_multi_cpu_programs_and_selected_clock_isolation(self):
        circuit = Circuit()
        first_ids = manually_wired_cpu(circuit, "MOV R0, 7\nHLT\n", 0)
        second_ids = manually_wired_cpu(circuit, "MOV R0, 19\nHLT\n", 3000)
        candidates = discover_cpus(circuit)
        self.assertEqual(len(candidates), 2)
        first = bind_cpu(circuit, next(c for c in candidates if c.ids["control"] == first_ids["control"]),
                         "First", "MOV R0, 7\nHLT\n")
        second = bind_cpu(circuit, next(c for c in candidates if c.ids["control"] == second_ids["control"]),
                          "Second", "MOV R0, 19\nHLT\n")
        simulator = Simulator(circuit)
        CpuStepper(simulator, binding=second).step_instruction()
        self.assertEqual(circuit.components[second_ids["registers"]].state["words"]["0"], 19)
        self.assertEqual(circuit.components[first_ids["registers"]].state.get("words", {}), {})
        self.assertEqual(circuit.components[first_ids["control"]].state.get("instructions", 0), 0)
        select_cpu(circuit, first["id"])
        simulator.evaluate()
        CpuStepper(simulator, binding=first).step_instruction()
        self.assertEqual(circuit.components[first_ids["registers"]].state["words"]["0"], 7)
        self.assertEqual(circuit.components[second_ids["registers"]].state["words"]["0"], 19)
        self.assertFalse(circuit.components[second_ids["clock"]].params["running"])
        self.assertTrue(circuit.components[first_ids["clock"]].params["running"])
        restored = Circuit.from_dict(json.loads(json.dumps(circuit.to_dict())))
        self.assertEqual(len(get_bindings(restored)), 2)
        self.assertEqual(get_active_binding(restored)["id"], first["id"])

    def test_legacy_board_works_after_binding_and_rebinding(self):
        circuit = create_cpu_circuit("HLT\n")
        original = circuit.cpu_workspace["ids"]
        bound = bind_cpu(circuit, discover_cpus(circuit)[0])
        self.assertEqual(bound["ids"], original)
        self.assertEqual(len(get_bindings(circuit)), 1)
        self.assertEqual(rebind_cpu(circuit, bound["id"], discover_cpus(circuit)[0])["ids"], original)

    def test_rebind_replaced_components_without_stale_ids(self):
        circuit = Circuit(); old = manually_wired_cpu(circuit, "HLT\n")
        binding = bind_cpu(circuit, discover_cpus(circuit)[0], source="HLT\n")
        replacements = copy_selection(circuit, list(old.values()), 2200, 0)
        for cid in old.values(): circuit.remove(cid)
        candidate, = discover_cpus(circuit)
        self.assertTrue(candidate.compatible)
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_board(circuit, binding)
        rebind_cpu(circuit, binding["id"], candidate)
        self.assertEqual(validate_board(circuit), candidate.ids)
        self.assertEqual(len(replacements), len(ROLES))

    def test_deleted_bound_component_remains_viewable_after_reopen(self):
        circuit = Circuit(); manually_wired_cpu(circuit, "HLT\n")
        binding = bind_cpu(circuit, discover_cpus(circuit)[0])
        circuit.remove(binding["ids"]["rom"])
        reopened = Circuit.from_dict(json.loads(json.dumps(circuit.to_dict())))
        self.assertEqual(len(get_bindings(reopened)), 1)
        self.assertFalse(discover_cpus(reopened)[0].compatible)
        with self.assertRaisesRegex(ValueError, "rom"):
            validate_board(reopened)

    def test_profile_is_portable_and_checked_against_real_circuit(self):
        circuit = Circuit(); manually_wired_cpu(circuit, "HLT\n")
        candidate, = discover_cpus(circuit)
        binding = bind_cpu(circuit, candidate)
        profile = json.loads(export_profile(binding))
        other = Circuit(); manually_wired_cpu(other, "HLT\n")
        self.assertTrue(match_profile(discover_cpus(other)[0], profile))
        profile["address_bits"] = 16
        with self.assertRaisesRegex(ValueError, "address_bits"):
            match_profile(discover_cpus(other)[0], profile)

    def test_second_binding_requires_separate_clock(self):
        circuit = Circuit(); ids = manually_wired_cpu(circuit, "HLT\n")
        first = bind_cpu(circuit, discover_cpus(circuit)[0])
        second_ids = manually_wired_cpu(circuit, "HLT\n", 3000)
        for wire in circuit.wires.values():
            if wire.source == second_ids["clock"]: wire.source = ids["clock"]
        second = next(c for c in discover_cpus(circuit) if c.ids["control"] == second_ids["control"])
        self.assertTrue(second.compatible)
        with self.assertRaisesRegex(ValueError, "separate Clock"):
            bind_cpu(circuit, second)
        self.assertIsNotNone(first)


class ProgrammingTests(unittest.TestCase):
    def test_bin_hex_program_selected_rom_and_validate(self):
        circuit = Circuit(); ids = manually_wired_cpu(circuit, "HLT\n")
        binding = bind_cpu(circuit, discover_cpus(circuit)[0])
        program = assemble("MOV R0, 31\nHLT\n")
        self.assertEqual(parse_intel_hex(program.intel_hex()), program.image[:4])
        self.assertEqual(load_rom_image(circuit, program.image[:4], binding), 4)
        self.assertEqual(circuit.components[ids["rom"]].params["contents"]["2"], 31)
        load_program(circuit, "MOV R0, 31\nHLT\n", binding)
        self.assertTrue(program_matches_rom(circuit, program, binding))
        with self.assertRaisesRegex(ValueError, "1–256"):
            load_rom_image(circuit, bytes(257), binding)
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_intel_hex(":0100000001FF\n:00000001FF\n")

    def test_programming_one_rom_preserves_another(self):
        circuit = Circuit()
        first_ids = manually_wired_cpu(circuit, "HLT\n")
        second_ids = manually_wired_cpu(circuit, "HLT\n", 3000)
        candidates = discover_cpus(circuit)
        first = bind_cpu(circuit, next(c for c in candidates if c.ids["control"] == first_ids["control"]))
        bind_cpu(circuit, next(c for c in candidates if c.ids["control"] == second_ids["control"]))
        other_rom = dict(circuit.components[second_ids["rom"]].params["contents"])
        load_rom_image(circuit, bytes((0x10, 0, 0x31, 0x01)), first)
        self.assertEqual(circuit.components[first_ids["rom"]].params["contents"]["2"], 0x31)
        self.assertEqual(circuit.components[second_ids["rom"]].params["contents"], other_rom)

    def test_selected_cpu_breakpoint_and_time_travel(self):
        circuit = Circuit(); ids = manually_wired_cpu(circuit, "MOV R0, 5\nHLT\n")
        binding = bind_cpu(circuit, discover_cpus(circuit)[0], source="MOV R0, 5\nHLT\n")
        sim = Simulator(circuit); history = SimulationHistory(sim)
        manager = CpuBreakpointManager(); manager.bind(circuit, binding)
        manager.add("address", 0); manager.add("register", 0, 5)
        found = []
        for _ in range(20):
            sim.step(); history.record(sim); found += manager.check(sim)
            if circuit.components[ids["control"]].state.get("instructions", 0) == 1: break
        self.assertEqual({event.reason for event in found}, {"address", "register"})
        final_step = circuit.tick
        history.navigate(sim, 0)
        self.assertEqual(circuit.components[ids["registers"]].state, {})
        for _ in range(final_step): sim.step()
        self.assertEqual(circuit.components[ids["registers"]].state["words"]["0"], 5)

    def test_time_travel_restores_active_clock_binding(self):
        circuit = Circuit()
        first_ids = manually_wired_cpu(circuit, "HLT\n")
        second_ids = manually_wired_cpu(circuit, "HLT\n", 3000)
        candidates = discover_cpus(circuit)
        first = bind_cpu(circuit, next(c for c in candidates if c.ids["control"] == first_ids["control"]))
        sim = Simulator(circuit); history = SimulationHistory(sim)
        first_branch = history.active_branch
        second = bind_cpu(circuit, next(c for c in candidates if c.ids["control"] == second_ids["control"]))
        sim.evaluate(); history.record_mutation(sim)
        self.assertEqual(get_active_binding(circuit)["id"], second["id"])
        history.navigate(sim, 0, first_branch)
        sync_active_from_clocks(circuit)
        self.assertEqual(get_active_binding(circuit)["id"], first["id"])
