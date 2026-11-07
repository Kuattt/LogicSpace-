"""Build two manifest-free example projects using public component/wire APIs."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cpu_architecture import REQUIRED_LINKS, ROLES, bind_cpu, discover_cpus
from cpu_isa import assemble
from engine import Circuit, Simulator


def add_wired_cpu(circuit, source, x):
    program = assemble(source)
    settings = {
        "clock": {"period": 2}, "enable": {"value": 1}, "reset": {"value": 0},
        "pc": {"width": 8}, "ir": {"width": 8},
        "rom": {"address_bits": 8, "data_bits": 8, "depth": 256,
                "contents": {str(a): program.image[a] for a in program.used_addresses}},
        "ram": {"address_bits": 8, "data_bits": 8, "depth": 256},
        "registers": {"registers": 4, "data_bits": 8, "read_ports": 2},
        "alu": {"width": 8},
        **{role: {"width": 8} for role in
           ("rf_imm", "rf_mem", "rf_reg", "pc_data", "mem_data")},
    }
    ids = {}
    for index, (role, kind) in enumerate(ROLES.items()):
        c = circuit.add(kind, x + index % 5 * 300, index // 5 * 340,
                        {"label": role, **settings.get(role, {})})
        ids[role] = c.id
    for source_role, output, target_role, input_pin, width in REQUIRED_LINKS:
        if width == 1:
            circuit.connect(ids[source_role], output, ids[target_role], input_pin)
        else:
            circuit.connect_bus(ids[source_role], output, ids[target_role], input_pin)
    candidate = next(c for c in discover_cpus(circuit) if c.ids["control"] == ids["control"])
    if candidate.issues: raise ValueError("Invalid example CPU: " + "; ".join(candidate.issues))
    return candidate


def main():
    target = Path(__file__).resolve().parent / "universal_cpu"
    target.mkdir(exist_ok=True)
    one = Circuit()
    source = "MOV R0, 12\nMOV R1, 3\nADD R0, R1\nHLT\n"
    bind_cpu(one, add_wired_cpu(one, source, 0), "Hand-wired arithmetic", source)
    if Simulator(one).errors: raise ValueError("Single CPU has simulation errors")
    one.save(target / "hand_wired.json")
    (target / "hand_wired.asm").write_text(source, encoding="utf-8")

    dual = Circuit()
    first = "MOV R0, 7\nHLT\n"
    second = "MOV R0, 19\nHLT\n"
    bind_cpu(dual, add_wired_cpu(dual, first, 0), "CPU A", first)
    bind_cpu(dual, add_wired_cpu(dual, second, 3000), "CPU B", second)
    if Simulator(dual).errors: raise ValueError("Dual CPU has simulation errors")
    dual.save(target / "two_cpus.json")
    (target / "cpu_a.asm").write_text(first, encoding="utf-8")
    (target / "cpu_b.asm").write_text(second, encoding="utf-8")


if __name__ == "__main__": main()
