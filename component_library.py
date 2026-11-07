"""Persistent, validated snapshots of LogicSpace custom blocks (no Qt dependency)."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import tempfile
import uuid

from engine import Circuit, pins

FORMAT = "logicspace-library-component"
DEFAULT_CATEGORIES = ("Arithmetic", "Memory", "Registers", "Counters", "CPU", "Custom")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _name(value, what):
    if not isinstance(value, str) or not value.strip() or value.strip() in (".", "..") or any(
            char in value for char in ("/", "\\", "\0")):
        raise ValueError(f"Invalid {what}")
    return value.strip()


def _atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".logicspace-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_definition(definition, name="block", stack=()):
    """Check the existing block format, terminals, nested dependencies and recursion."""
    if not isinstance(definition, dict):
        raise ValueError(f"{name}: block definition must be an object")
    required = ("inputs", "outputs", "input_map", "output_map", "circuit")
    if any(key not in definition for key in required):
        raise ValueError(f"{name}: missing block interface or circuit")
    if not isinstance(definition["circuit"], dict):
        raise ValueError(f"{name}: circuit must be an object")
    try:
        circuit = Circuit.from_dict(definition["circuit"])
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError(f"{name}: invalid internal circuit: {error}") from error
    for direction, terminal_kind, pin_direction in (("input", "INPUT", 1), ("output", "OUTPUT", 0)):
        labels = definition[direction + "s"]
        mapping = definition[direction + "_map"]
        if (not isinstance(labels, list) or not labels or any(not isinstance(x, str) for x in labels)
                or not isinstance(mapping, dict)
                or len(labels) != len(set(labels)) or set(labels) != set(mapping)):
            raise ValueError(f"{name}: invalid {direction} interface")
        used = set()
        for label in labels:
            _name(label, f"{direction} pin name")
            target = mapping[label]
            if isinstance(target, str):
                cid, pin = target, "Q" if direction == "input" else "A"
            elif isinstance(target, list) and len(target) == 2 and all(isinstance(x, str) for x in target):
                cid, pin = target
            else:
                raise ValueError(f"{name}: invalid mapping for {label}")
            component = circuit.components.get(cid)
            if component is None or component.kind != terminal_kind or pin not in pins(component, circuit.blocks)[pin_direction]:
                raise ValueError(f"{name}: {label} references a missing or incorrect terminal pin")
            if (cid, pin) in used:
                raise ValueError(f"{name}: terminal pin is mapped more than once")
            used.add((cid, pin))
    if "_hdl_bus_ports" in definition:
        grouped = definition["_hdl_bus_ports"]
        if not isinstance(grouped, dict) or set(grouped) != {"input", "output"}:
            raise ValueError(f"{name}: invalid HDL bus metadata")
        for direction in ("input", "output"):
            ports = grouped[direction]
            if not isinstance(ports, dict):
                raise ValueError(f"{name}: invalid HDL {direction} buses")
            for port, labels in ports.items():
                if (not isinstance(port, str) or not isinstance(labels, list)
                        or len(labels) not in (2, 4, 8, 16, 32)
                        or labels != [f"{port}{index}" for index in range(len(labels))]
                        or any(label not in definition[direction + "_map"] for label in labels)):
                    raise ValueError(f"{name}: invalid HDL bus {port}")
    if "designer" in definition:
        design = definition["designer"]
        if not isinstance(design, dict) or not isinstance(design.get("appearance"), dict) or not isinstance(design.get("terminals"), dict):
            raise ValueError(f"{name}: invalid designer metadata")
        appearance, layout = design["appearance"], design["terminals"]
        if (not re.fullmatch(r"#[0-9a-fA-F]{6}", str(appearance.get("body_color", "")))
                or any(not isinstance(appearance.get(key), int) or not 100 <= appearance[key] <= 520
                       for key in ("width", "height"))
                or any(not isinstance(appearance.get(key), str) for key in ("label", "short_description"))):
            raise ValueError(f"{name}: invalid body appearance")
        if set(layout) != set(definition["inputs"] + definition["outputs"]):
            raise ValueError(f"{name}: designer terminal positions do not match the interface")
        for label, info in layout.items():
            if (not isinstance(info, dict) or info.get("side") not in ("LEFT", "RIGHT", "TOP", "BOTTOM")
                    or not isinstance(info.get("order"), int) or info["order"] < 0
                    or not isinstance(info.get("description"), str)):
                raise ValueError(f"{name}: invalid placement for terminal {label}")
    next_stack = stack + (name,)
    for component in circuit.components.values():
        if component.kind.startswith("BLOCK:"):
            dependency = component.kind[6:]
            if dependency in next_stack:
                raise ValueError("Recursive component reference: " + " → ".join(next_stack + (dependency,)))
            nested = circuit.blocks.get(dependency)
            if nested is None:
                raise ValueError(f"{name}: missing dependency {dependency}")
            validate_definition(nested, dependency, next_stack)
    return deepcopy(definition)


class ComponentLibrary:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path.home() / ".local/share/logicspace/component_library"
        self.root.mkdir(parents=True, exist_ok=True)
        for category in DEFAULT_CATEGORIES:
            (self.root / category).mkdir(exist_ok=True)

    def categories(self):
        return sorted(path.name for path in self.root.iterdir() if path.is_dir() and not path.is_symlink())

    def create_category(self, name):
        name = _name(name, "category name")
        path = self.root / name
        if path.exists():
            raise ValueError("Category already exists")
        path.mkdir()
        return name

    def rename_category(self, old, new):
        new = _name(new, "category name")
        source, target = self.root / old, self.root / new
        if old not in self.categories() or target.exists():
            raise ValueError("Category missing or new name already exists")
        entries = self.list_entries(category=old)
        source.rename(target)
        for entry in entries:
            entry["category"], entry["modified"] = new, _now()
            _atomic_json(target / (entry["id"] + ".json"), entry)

    def scan(self):
        entries, errors = [], []
        for category in self.categories():
            for path in sorted((self.root / category).glob("*.json")):
                try:
                    if path.is_symlink():
                        raise ValueError("Symbolic links are not accepted")
                    entry = json.loads(path.read_text(encoding="utf-8"))
                    self.validate_entry(entry)
                    if entry["category"] != category or path.stem != entry["id"]:
                        raise ValueError("File location does not match component metadata")
                    entries.append(entry)
                except (OSError, ValueError, TypeError, KeyError) as error:
                    errors.append(f"{path.name}: {error}")
        ids = [entry["id"] for entry in entries]
        if len(ids) != len(set(ids)):
            errors.append("Duplicate stable component IDs in library")
        return entries, errors

    def list_entries(self, query="", category=None, favorites=False):
        entries, _ = self.scan()
        query = query.casefold().strip()
        return sorted((entry for entry in entries if (category is None or entry["category"] == category)
                       and (not favorites or entry["favorite"])
                       and (not query or query in (entry["name"] + " " + entry["description"] + " " + entry["category"]).casefold())),
                      key=lambda entry: (entry["category"].casefold(), entry["name"].casefold()))

    @staticmethod
    def validate_entry(entry):
        if not isinstance(entry, dict) or entry.get("format") != FORMAT or entry.get("schema_version") != 1:
            raise ValueError("Unsupported library component format")
        try:
            uuid.UUID(entry["id"])
            _name(entry["name"], "component name")
            _name(entry["category"], "category name")
            if not isinstance(entry["description"], str) or not isinstance(entry["version"], int) or entry["version"] < 1:
                raise ValueError("Invalid component metadata")
            if not isinstance(entry["favorite"], bool):
                raise ValueError("Invalid favorite flag")
            datetime.fromisoformat(entry["created"])
            datetime.fromisoformat(entry["modified"])
            validate_definition(entry["definition"], entry["name"])
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"Invalid library component metadata: {error}") from error
        return entry

    def get(self, component_id):
        matches = [entry for entry in self.list_entries() if entry["id"] == component_id]
        if len(matches) != 1:
            raise ValueError("Library component missing or duplicated")
        return deepcopy(matches[0])

    def save(self, name, definition, category="Custom", description=""):
        name, category = _name(name, "component name"), _name(category, "category name")
        if category not in self.categories():
            self.create_category(category)
        definition = validate_definition(definition, name)
        if any(e["name"].casefold() == name.casefold() and e["category"] == category for e in self.list_entries()):
            raise ValueError("A component with this name already exists in the category")
        timestamp = _now()
        entry = {"format": FORMAT, "schema_version": 1, "id": str(uuid.uuid4()), "name": name,
                 "description": description, "category": category, "version": 1,
                 "created": timestamp, "modified": timestamp, "favorite": False,
                 "definition": definition}
        self.validate_entry(entry)
        _atomic_json(self.root / category / (entry["id"] + ".json"), entry)
        return entry

    def _write(self, entry, old_category=None):
        self.validate_entry(entry)
        destination = self.root / entry["category"] / (entry["id"] + ".json")
        _atomic_json(destination, entry)
        if old_category and old_category != entry["category"]:
            (self.root / old_category / (entry["id"] + ".json")).unlink(missing_ok=True)
        return entry

    def update(self, component_id, *, name=None, description=None, category=None, favorite=None, definition=None):
        entry = self.get(component_id)
        old_category = entry["category"]
        if name is not None: entry["name"] = _name(name, "component name")
        if description is not None: entry["description"] = description
        if category is not None:
            entry["category"] = _name(category, "category name")
            if entry["category"] not in self.categories(): self.create_category(entry["category"])
        if any(other["id"] != component_id and other["category"] == entry["category"]
               and other["name"].casefold() == entry["name"].casefold() for other in self.list_entries()):
            raise ValueError("A component with this name already exists in the category")
        if favorite is not None: entry["favorite"] = bool(favorite)
        if definition is not None:
            entry["definition"] = validate_definition(definition, entry["name"])
            entry["version"] += 1
        entry["modified"] = _now()
        return self._write(entry, old_category)

    def duplicate(self, component_id, name=None):
        source = self.get(component_id)
        return self.save(name or source["name"] + " Copy", source["definition"],
                         source["category"], source["description"])

    def delete(self, component_id):
        entry = self.get(component_id)
        (self.root / entry["category"] / (entry["id"] + ".json")).unlink()

    def export(self, component_id, path):
        _atomic_json(Path(path), self.get(component_id))

    def import_json(self, path, category=None):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("format") == FORMAT:
            self.validate_entry(data)
            return self.save(data["name"], data["definition"], category or data["category"], data["description"])
        if isinstance(data, dict) and data.get("format") == "logicspace":
            circuit = Circuit.from_dict(data)
            definition = block_definition_from_circuit(circuit)
            return self.save(Path(path).stem, definition, category or "Custom")
        if isinstance(data, dict) and all(key in data for key in
                                          ("inputs", "outputs", "input_map", "output_map", "circuit")):
            return self.save(Path(path).stem, data, category or "Custom")
        raise ValueError("Choose a LogicSpace library component or circuit JSON file")

    def install_into(self, circuit, component_id):
        entry = self.get(component_id)
        definition = deepcopy(entry["definition"])
        definition["_library"] = {"id": entry["id"], "version": entry["version"],
                                  "name": entry["name"]}
        name = entry["name"]
        if name in circuit.blocks and circuit.blocks[name] != definition:
            suffix = 2
            while f"{name} {suffix}" in circuit.blocks:
                suffix += 1
            name = f"{name} {suffix}"
        circuit.blocks.setdefault(name, definition)
        return name


def block_definition_from_circuit(sub):
    """Build the legacy block format from selected INPUT/OUTPUT terminals."""
    inputs, outputs = {}, {}
    for component in sub.components.values():
        if component.kind == "INPUT":
            label = str(component.params.get("label") or f"IN{len(inputs) + 1}")
            for pin in pins(component, sub.blocks)[1]:
                external = label if pin == "Q" else label + pin[1:]
                while external in inputs: external += "_"
                inputs[external] = component.id if pin == "Q" else [component.id, pin]
        elif component.kind == "OUTPUT":
            label = str(component.params.get("label") or f"OUT{len(outputs) + 1}")
            for pin in pins(component, sub.blocks)[0]:
                external = label if pin == "A" else label + pin[1:]
                while external in outputs: external += "_"
                outputs[external] = component.id if pin == "A" else [component.id, pin]
    if not inputs or not outputs:
        raise ValueError("A block needs at least one INPUT and one OUTPUT component as external terminals")
    definition = {"inputs": list(inputs), "outputs": list(outputs), "input_map": inputs,
                  "output_map": outputs, "circuit": sub.to_dict()}
    return validate_definition(definition)
