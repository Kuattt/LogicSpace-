import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from component_library import ComponentLibrary, block_definition_from_circuit, validate_definition
from engine import Circuit, Simulator


def inverter():
    circuit = Circuit()
    source = circuit.add("INPUT", params={"label": "A", "width": 2})
    gate = circuit.add("NOT", params={"width": 2})
    target = circuit.add("OUTPUT", params={"label": "Y", "width": 2})
    for bit in range(2):
        circuit.connect(source.id, f"Q{bit}", gate.id, f"A{bit}")
        circuit.connect(gate.id, f"Q{bit}", target.id, f"A{bit}")
    return circuit


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.library = ComponentLibrary(self.temporary.name)
        self.definition = block_definition_from_circuit(inverter())

    def save(self, name="Invert"):
        return self.library.save(name, self.definition, "Custom", "Two bit inverter")

    def test_save_and_load_in_another_project_with_unique_instances(self):
        entry = self.save()
        project = Circuit()
        name = self.library.install_into(project, entry["id"])
        self.assertEqual(project.blocks[name]["_library"],
                         {"id": entry["id"], "version": 1, "name": "Invert"})
        input_part = project.add("INPUT", params={"width": 2, "value": 1})
        first = project.add("BLOCK:" + name)
        second = project.add("BLOCK:" + name)
        self.assertNotEqual(first.id, second.id)
        for bit in range(2):
            project.connect(input_part.id, f"Q{bit}", first.id, f"A{bit}")
        sim = Simulator(project)
        self.assertEqual([sim.outputs[first.id, f"Y{bit}"] for bit in range(2)], [0, 1])
        saved = Path(self.temporary.name) / "project-b.json"
        project.save(saved)
        reopened = Circuit.load(saved)
        self.assertEqual([Simulator(reopened).outputs[first.id, f"Y{bit}"] for bit in range(2)], [0, 1])

    def test_search_categories_favorites_and_rename(self):
        self.library.create_category("My Circuits")
        entry = self.library.save("Bit Flip", self.definition, "My Circuits", "inverts two bits")
        self.assertEqual(len(self.library.list_entries("inverts")), 1)
        self.assertEqual(len(self.library.list_entries(category="My Circuits")), 1)
        self.library.update(entry["id"], favorite=True, name="Two Bit Flip")
        self.assertEqual(self.library.list_entries(favorites=True)[0]["name"], "Two Bit Flip")
        self.library.rename_category("My Circuits", "Signals")
        self.assertEqual(self.library.get(entry["id"])["category"], "Signals")

    def test_duplicate_and_import_export(self):
        entry = self.save()
        duplicate = self.library.duplicate(entry["id"])
        self.assertNotEqual(entry["id"], duplicate["id"])
        exported = Path(self.temporary.name) / "export.json"
        self.library.export(entry["id"], exported)
        self.assertEqual(json.loads(exported.read_text())["definition"], self.definition)
        imported = self.library.import_json(exported, category="Arithmetic")
        self.assertNotEqual(imported["id"], entry["id"])
        self.assertEqual(imported["category"], "Arithmetic")
        circuit_file = Path(self.temporary.name) / "circuit.json"
        inverter().save(circuit_file)
        from_circuit = self.library.import_json(circuit_file)
        self.assertEqual(from_circuit["definition"]["inputs"], ["A0", "A1"])
        raw_file = self._write("raw-block.json", self.definition)
        from_raw = self.library.import_json(raw_file)
        self.assertEqual(from_raw["definition"]["outputs"], ["Y0", "Y1"])

    def test_invalid_connections_duplicate_ids_and_corrupt_json(self):
        bad = inverter().to_dict()
        bad["components"].append(dict(bad["components"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate component ID"):
            self.library.import_json(self._write("duplicate.json", bad))
        bad = inverter().to_dict()
        bad["wires"][0]["source_pin"] = "NO_SUCH_PIN"
        with self.assertRaises(ValueError):
            self.library.import_json(self._write("bad-wire.json", bad))
        broken = Path(self.temporary.name) / "Custom" / "broken.json"
        broken.write_text("{bad")
        entries, errors = self.library.scan()
        self.assertFalse(entries)
        self.assertTrue(any("broken.json" in issue for issue in errors))

    def _write(self, filename, data):
        path = Path(self.temporary.name) / filename
        path.write_text(json.dumps(data))
        return path

    def test_missing_and_recursive_dependencies(self):
        leaf = Circuit()
        leaf_input = leaf.add("INPUT")
        leaf_output = leaf.add("OUTPUT")
        leaf.connect(leaf_input.id, "Q", leaf_output.id, "A")
        leaf_definition = block_definition_from_circuit(leaf)
        circuit = Circuit()
        circuit.blocks["Child"] = leaf_definition
        source = circuit.add("INPUT")
        nested = circuit.add("BLOCK:Child")
        target = circuit.add("OUTPUT")
        circuit.connect(source.id, "Q", nested.id, "IN1")
        circuit.connect(nested.id, "OUT1", target.id, "A")
        definition = block_definition_from_circuit(circuit)
        # A referenced dependency cannot disappear from the embedded snapshot.
        definition["circuit"]["blocks"].pop("Child")
        with self.assertRaises(ValueError):
            validate_definition(definition)
        with self.assertRaisesRegex(ValueError, "Recursive"):
            validate_definition(block_definition_from_circuit(circuit), "Child")

    def test_version_update_delete_and_project_independence(self):
        entry = self.save()
        project = Circuit()
        name = self.library.install_into(project, entry["id"])
        original = json.dumps(project.blocks[name], sort_keys=True)
        replacement = json.loads(json.dumps(self.definition))
        replacement["circuit"]["components"][1]["kind"] = "NO_SUCH_KIND"
        with self.assertRaises(ValueError):
            self.library.update(entry["id"], definition=replacement)
        updated = self.library.update(entry["id"], definition=self.definition)
        self.assertEqual(updated["version"], 2)
        self.library.update(entry["id"], name="New Name")
        self.library.delete(entry["id"])
        self.assertEqual(json.dumps(project.blocks[name], sort_keys=True), original)
        self.assertEqual(Circuit.from_dict(project.to_dict()).validate(), [])

    def test_legacy_custom_block_format_is_accepted(self):
        legacy = {"inputs": ["A0", "A1"], "outputs": ["Y0", "Y1"],
                  "input_map": self.definition["input_map"], "output_map": self.definition["output_map"],
                  "circuit": self.definition["circuit"]}
        entry = self.library.save("Legacy", legacy)
        project = Circuit()
        name = self.library.install_into(project, entry["id"])
        self.assertEqual(project.add("BLOCK:" + name).kind, "BLOCK:Legacy")

    def test_new_instance_id_retries_collision(self):
        circuit = Circuit()
        old = circuit.add("INPUT")
        with patch("engine.new_id", side_effect=[old.id, "fresh-id"]):
            new = circuit.add("INPUT")
        self.assertEqual(new.id, "fresh-id")
        self.assertEqual(len(circuit.components), 2)


if __name__ == "__main__":
    unittest.main()
