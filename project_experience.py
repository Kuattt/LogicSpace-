"""Local templates, project gallery and safe data-only project packages."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import json
import os
import shutil
import tempfile
import uuid
import zipfile

from engine import Circuit, Simulator
from cpu_board import create_cpu_circuit


APP_DATA = Path.home() / ".local/share/logicspace"
CATEGORIES = ("Logic Gates", "Combinational Circuits", "Sequential Circuits",
              "ALU", "RAM / ROM", "Register File", "8-bit CPU",
              "CPU with Assembly", "Custom CPU")
DIFFICULTIES = ("Beginner", "Intermediate", "Advanced")


@dataclass(frozen=True)
class TemplateInfo:
    id: str
    name: str
    category: str
    difficulty: str
    description: str
    builtin: bool


BUILTIN_TEMPLATES = (
    TemplateInfo("logic_gates", "AND gate lab", CATEGORIES[0], "Beginner", "Two switches drive an AND gate and output indicator.", True),
    TemplateInfo("combinational", "Half adder", CATEGORIES[1], "Beginner", "Sum and carry from two one-bit inputs.", True),
    TemplateInfo("sequential", "D flip-flop", CATEGORIES[2], "Intermediate", "Drive D and CLK to inspect stored Q.", True),
    TemplateInfo("alu", "8-bit ALU", CATEGORIES[3], "Intermediate", "Two 8-bit operands and a 4-bit operation bus.", True),
    TemplateInfo("memory", "RAM and ROM", CATEGORIES[4], "Intermediate", "Read ROM and write RAM using shared address/data controls.", True),
    TemplateInfo("register_file", "Register File", CATEGORIES[5], "Intermediate", "Four 8-bit registers with two independent read ports.", True),
    TemplateInfo("cpu", "8-bit CPU starter", CATEGORIES[6], "Advanced", "Wired ISA 2.1 CPU with NOP and HLT in ROM.", True),
    TemplateInfo("cpu_assembly", "CPU with Assembly", CATEGORIES[7], "Advanced", "Wired CPU with an arithmetic Assembly program.", True),
    TemplateInfo("custom_cpu", "Hand-wired CPU", CATEGORIES[8], "Advanced", "Manifest-free CPU project discovered through physical connections.", True),
)
BUILTIN_BY_ID = {item.id: item for item in BUILTIN_TEMPLATES}


def _wire(circuit, source, output, target, input_pin, bus=False):
    if bus: circuit.connect_bus(source.id, output, target.id, input_pin)
    else: circuit.connect(source.id, output, target.id, input_pin)


def _basic_template(identifier):
    c = Circuit()
    if identifier == "logic_gates":
        a = c.add("INPUT", -240, -80, {"label": "A", "value": 0})
        b = c.add("INPUT", -240, 80, {"label": "B", "value": 1})
        gate = c.add("AND", 0, 0)
        y = c.add("OUTPUT", 250, 0, {"label": "Y"})
        _wire(c, a, "Q", gate, "A"); _wire(c, b, "Q", gate, "B"); _wire(c, gate, "Q", y, "A")
    elif identifier == "combinational":
        a = c.add("INPUT", -240, -80, {"label": "A"})
        b = c.add("INPUT", -240, 80, {"label": "B"})
        gate = c.add("Half Adder", 0, 0)
        s = c.add("OUTPUT", 260, -80, {"label": "SUM"})
        carry = c.add("OUTPUT", 260, 80, {"label": "CARRY"})
        _wire(c, a, "Q", gate, "A"); _wire(c, b, "Q", gate, "B")
        _wire(c, gate, "SUM", s, "A"); _wire(c, gate, "CARRY", carry, "A")
    elif identifier == "sequential":
        d = c.add("INPUT", -240, -70, {"label": "D"})
        clk = c.add("INPUT", -240, 90, {"label": "CLK"})
        flip = c.add("D Flip-Flop", 0, 0)
        q = c.add("OUTPUT", 260, 0, {"label": "Q"})
        _wire(c, d, "Q", flip, "D"); _wire(c, clk, "Q", flip, "CLK"); _wire(c, flip, "Q", q, "A")
    elif identifier == "alu":
        a = c.add("Bus Input", -260, -120, {"label": "A", "width": 8, "value": 5})
        b = c.add("Bus Input", -260, 40, {"label": "B", "width": 8, "value": 3})
        op = c.add("Bus Input", -260, 210, {"label": "OP", "width": 4, "value": 0})
        alu = c.add("ALU", 40, 30, {"width": 8})
        q = c.add("Bus Probe", 340, 30, {"label": "RESULT", "width": 8})
        for s, sp, tp in ((a, "Q", "A"), (b, "Q", "B"), (op, "Q", "OP")):
            _wire(c, s, sp, alu, tp, True)
        _wire(c, alu, "Q", q, "D", True)
    elif identifier == "memory":
        address = c.add("Bus Input", -300, -150, {"label": "ADDRESS", "width": 8, "value": 0})
        data = c.add("Bus Input", -300, 20, {"label": "DATA", "width": 8, "value": 0x2A})
        we = c.add("INPUT", -300, 180, {"label": "WE"})
        clk = c.add("INPUT", -300, 300, {"label": "CLK"})
        rom = c.add("ROM", 20, -200, {"address_bits": 8, "data_bits": 8, "depth": 256,
                                        "contents": {"0": 0xA5, "1": 0x5A}})
        ram = c.add("RAM", 20, 170, {"address_bits": 8, "data_bits": 8, "depth": 256})
        rq = c.add("Bus Probe", 340, -200, {"label": "ROM_Q", "width": 8})
        mq = c.add("Bus Probe", 340, 170, {"label": "RAM_Q", "width": 8})
        for m in (rom, ram): _wire(c, address, "Q", m, "A", True)
        _wire(c, data, "Q", ram, "D", True); _wire(c, we, "Q", ram, "WE")
        _wire(c, clk, "Q", ram, "CLK"); _wire(c, rom, "Q", rq, "D", True)
        _wire(c, ram, "Q", mq, "D", True)
    elif identifier == "register_file":
        rf = c.add("Register File", 0, 0, {"registers": 4, "data_bits": 8, "read_ports": 2})
        for label, width, y, port in (("RA0", 2, -320, "RA0"), ("RA1", 2, -170, "RA1"),
                                      ("WA", 2, -20, "WA"), ("D", 8, 130, "D")):
            input_bus = c.add("Bus Input", -300, y, {"label": label, "width": width})
            _wire(c, input_bus, "Q", rf, port, True)
        for label, y in (("WE", 270), ("CLK", 380)):
            switch = c.add("INPUT", -300, y, {"label": label})
            _wire(c, switch, "Q", rf, label)
        for index, y in ((0, -100), (1, 120)):
            probe = c.add("Bus Probe", 340, y, {"label": f"R{index}", "width": 8})
            _wire(c, rf, f"R{index}", probe, "D", True)
    else: raise ValueError("Unknown built-in template")
    return c


def _builtin_circuit(identifier):
    if identifier in ("cpu", "cpu_assembly"):
        source = "NOP\nHLT\n" if identifier == "cpu" else "MOV R0, 10\nMOV R1, 5\nADD R0, R1\nHLT\n"
        return create_cpu_circuit(source)
    if identifier == "custom_cpu":
        return Circuit.load(Path(__file__).parent / "examples/universal_cpu/hand_wired.json")
    return _basic_template(identifier)


class TemplateStore:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else APP_DATA / "templates"
        self.issues = []

    def list(self):
        result = list(BUILTIN_TEMPLATES)
        self.issues = []
        if self.root.exists():
            for path in sorted(self.root.glob("*.json")):
                try:
                    data = self._read(path)
                    result.append(TemplateInfo(data["id"], data["name"], data["category"],
                                               data["difficulty"], data["description"], False))
                except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
                    self.issues.append(f"{path.name}: {error}")
        return result

    def _read(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        validate_template(data)
        return data

    def get_package(self, identifier):
        if identifier in BUILTIN_BY_ID: return None
        path = self.root / (identifier + ".json")
        if not path.is_file(): raise ValueError("User template is unavailable")
        return self._read(path)

    def create(self, identifier):
        if identifier in BUILTIN_BY_ID:
            info = BUILTIN_BY_ID[identifier]
            circuit = _builtin_circuit(identifier)
        else:
            data = self.get_package(identifier)
            info = TemplateInfo(data["id"], data["name"], data["category"],
                                data["difficulty"], data["description"], False)
            circuit = Circuit.from_dict(deepcopy(data["circuit"]))
        Simulator(circuit).reset()
        circuit.project_info = {"version": 1, "name": info.name,
                                "description": info.description, "source_template": info.id}
        return circuit

    def save(self, circuit, name, category="Custom CPU", difficulty="Intermediate", description=""):
        _validate_metadata(name, category, difficulty, description)
        copied = Circuit.from_dict(deepcopy(circuit.to_dict()))
        Simulator(copied).reset()
        identifier = uuid.uuid4().hex
        data = {"format": "logicspace-template", "version": 1, "id": identifier,
                "name": name.strip(), "category": category, "difficulty": difficulty,
                "description": description.strip(), "circuit": copied.to_dict()}
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.root / (identifier + ".json"), data)
        return identifier

    def install(self, data):
        validate_template(data)
        path = self.root / (data["id"] + ".json")
        if path.exists():
            if self._read(path) == data: return False
            raise FileExistsError("A different user template already has this ID")
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_json(path, data)
        return True


def _validate_metadata(name, category, difficulty, description):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError("Name must contain 1–80 characters")
    if category not in CATEGORIES: raise ValueError("Choose a supported category")
    if difficulty not in DIFFICULTIES: raise ValueError("Choose a supported difficulty")
    if not isinstance(description, str) or len(description) > 2000:
        raise ValueError("Description must contain at most 2000 characters")


def validate_template(data):
    if not isinstance(data, dict) or data.get("format") != "logicspace-template" or data.get("version") != 1:
        raise ValueError("Unsupported template format")
    identifier = data.get("id")
    if not isinstance(identifier, str) or len(identifier) != 32 or any(ch not in "0123456789abcdef" for ch in identifier):
        raise ValueError("Invalid template ID")
    _validate_metadata(data.get("name"), data.get("category"), data.get("difficulty"), data.get("description"))
    if not isinstance(data.get("circuit"), dict): raise ValueError("Template circuit is missing")
    Circuit.from_dict(data.get("circuit"))
    return True


def _atomic_json(path, data):
    path = Path(path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        temp_path = Path(temporary.name)
        json.dump(data, temporary, indent=2, ensure_ascii=False)
    try: os.replace(temp_path, path)
    finally: temp_path.unlink(missing_ok=True)


BUILTIN_GALLERY = (
    ("half_adder", "Half adder", "Combinational Circuits", "Beginner", "One-bit sum and carry", "examples/half_adder.json"),
    ("bus_adder", "8-bit bus adder", "ALU", "Intermediate", "Native 8-bit BusWire arithmetic", "examples/bus_8bit_adder.json"),
    ("cpu_2_0", "CPU datapath 2.0", "8-bit CPU", "Advanced", "Earlier CPU building example", "examples/cpu_8bit.json"),
    *(("assembly_" + name, name.title() + " Assembly", "CPU with Assembly", "Advanced",
       "Wired ISA 2.1 Assembly project", f"examples/assembly/{name}.json")
      for name in ("arithmetic", "loop", "memory", "fibonacci", "stack")),
    ("hand_wired", "Hand-wired CPU", "Custom CPU", "Advanced", "Manifest-free ISA 2.1 circuit", "examples/universal_cpu/hand_wired.json"),
    ("two_cpus", "Two independent CPUs", "Custom CPU", "Advanced", "Two ROM programs on one canvas", "examples/universal_cpu/two_cpus.json"),
)


class ProjectGallery:
    def __init__(self, registry=None):
        self.registry = Path(registry) if registry is not None else APP_DATA / "gallery.json"

    def _items(self):
        if not self.registry.exists(): return []
        data = json.loads(self.registry.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("items"), list):
            raise ValueError("Invalid gallery registry")
        for item in data["items"]:
            if (not isinstance(item, dict) or
                    any(not isinstance(item.get(key), str) for key in
                        ("id", "name", "category", "difficulty", "description", "path"))):
                raise ValueError("Invalid gallery entry")
        return data["items"]

    def list(self, query="", category="All", difficulty="All"):
        base = Path(__file__).parent
        items = [dict(id=uid, name=name, category=cat, difficulty=level,
                      description=description, path=str(base / path), builtin=True)
                 for uid, name, cat, level, description, path in BUILTIN_GALLERY]
        items.extend(dict(item, builtin=False) for item in self._items())
        query = query.casefold().strip()
        return [item for item in items
                if (not query or query in (item["name"] + " " + item["description"]).casefold())
                and (category == "All" or item["category"] == category)
                and (difficulty == "All" or item["difficulty"] == difficulty)]

    def add(self, path, name, category, difficulty, description=""):
        _validate_metadata(name, category, difficulty, description)
        path = Path(path).expanduser().resolve()
        Circuit.load(path)
        items = self._items()
        identifier = uuid.uuid4().hex
        items.append(dict(id=identifier, name=name.strip(), category=category,
                          difficulty=difficulty, description=description.strip(), path=str(path)))
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.registry, {"version": 1, "items": items})
        return identifier

    def remove(self, identifier):
        items = self._items()
        remaining = [item for item in items if item.get("id") != identifier]
        if len(remaining) == len(items): raise ValueError("User gallery entry not found")
        _atomic_json(self.registry, {"version": 1, "items": remaining})

    def open(self, identifier):
        item = next((item for item in self.list() if item["id"] == identifier), None)
        if item is None: raise ValueError("Gallery project not found")
        return Circuit.load(item["path"])

    def duplicate(self, identifier, destination):
        item = next((item for item in self.list() if item["id"] == identifier), None)
        if item is None: raise ValueError("Gallery project not found")
        destination = Path(destination)
        if destination.exists(): raise FileExistsError("Destination project already exists")
        Circuit.load(item["path"])  # Validate before copying.
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            with Path(item["path"]).open("rb") as source:
                shutil.copyfileobj(source, output)
        try: os.link(temporary, destination)
        finally: temporary.unlink(missing_ok=True)
        return destination


class ProjectPackage:
    @staticmethod
    def export(circuit, path, metadata, templates=None):
        _validate_metadata(metadata.get("name"), metadata.get("category"),
                           metadata.get("difficulty"), metadata.get("description", ""))
        project = Circuit.from_dict(deepcopy(circuit.to_dict())).to_dict()
        package_meta = {"format": "logicspace-package", "version": 1,
                        **{key: metadata.get(key, "") for key in
                           ("name", "category", "difficulty", "description")}}
        payloads = {"project.json": json.dumps(project, indent=2, ensure_ascii=False).encode(),
                    "metadata.json": json.dumps(package_meta, indent=2, ensure_ascii=False).encode(),
                    "README.md": ("# " + metadata["name"].strip() + "\n\n" +
                                  metadata.get("description", "").strip() + "\n").encode()}
        source_id = (circuit.project_info or {}).get("source_template")
        if source_id and source_id not in BUILTIN_BY_ID and templates is None:
            raise ValueError("A user-template project needs its template store for ZIP export")
        if templates is not None and source_id and source_id not in BUILTIN_BY_ID:
            template = templates.get_package(source_id)
            payloads[f"templates/{source_id}.json"] = json.dumps(template, indent=2, ensure_ascii=False).encode()
        path = Path(path)
        if path.exists(): raise FileExistsError("Destination package already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in payloads.items(): archive.writestr(name, data)
            os.replace(temporary_path, path)
        finally: temporary_path.unlink(missing_ok=True)
        return path

    @staticmethod
    def import_package(path, destination=None, templates=None):
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(names) != len(set(names)) or len(names) > 32:
                    raise ValueError("Duplicate or too many ZIP entries")
                if set(("project.json", "metadata.json", "README.md")) - set(names):
                    raise ValueError("Package needs project.json, metadata.json and README.md")
                if any(name not in ("project.json", "metadata.json", "README.md") and
                       not (name.startswith("templates/") and name.endswith(".json") and
                            len(Path(name).parts) == 2) for name in names):
                    raise ValueError("Unexpected or unsafe ZIP entry")
                if any(info.is_dir() or info.file_size > 25_000_000 or
                       info.external_attr >> 16 & 0o170000 == 0o120000 for info in infos):
                    raise ValueError("Unsafe or oversized ZIP entry")
                if sum(info.file_size for info in infos) > 50_000_000:
                    raise ValueError("ZIP package exceeds size limit")
                project_data = json.loads(archive.read("project.json"))
                if not isinstance(project_data, dict): raise ValueError("Project JSON must be an object")
                circuit = Circuit.from_dict(project_data)
                metadata = json.loads(archive.read("metadata.json"))
                if not isinstance(metadata, dict): raise ValueError("Metadata JSON must be an object")
                if metadata.get("format") != "logicspace-package" or metadata.get("version") != 1:
                    raise ValueError("Unsupported package version")
                _validate_metadata(metadata.get("name"), metadata.get("category"),
                                   metadata.get("difficulty"), metadata.get("description", ""))
                bundled = []
                for name in names:
                    if name.startswith("templates/"):
                        data = json.loads(archive.read(name))
                        validate_template(data)
                        if name != f"templates/{data['id']}.json":
                            raise ValueError("Template filename does not match ID")
                        bundled.append(data)
                source_id = (circuit.project_info or {}).get("source_template")
                if source_id and source_id not in BUILTIN_BY_ID and source_id not in {item["id"] for item in bundled}:
                    raise ValueError("Package is missing the project's user template")
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError,
                AttributeError, TypeError, RuntimeError) as error:
            raise ValueError(f"Invalid LogicSpace package: {error}") from error
        if templates is not None:
            for data in bundled:
                existing = templates.root / (data["id"] + ".json")
                if existing.exists() and templates._read(existing) != data:
                    raise FileExistsError("A different user template already has this ID")
        if destination is not None:
            destination = Path(destination)
            if destination.exists(): raise FileExistsError("Destination project already exists")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent,
                                             delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(project_data, stream, indent=2, ensure_ascii=False)
            try:
                # Linux hard-link creation is atomic and refuses an existing target.
                os.link(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        if templates is not None:
            for data in bundled: templates.install(data)
        return circuit, metadata, bundled
