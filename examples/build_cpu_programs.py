"""Regenerate all Assembly ROM images and wired example projects."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cpu_board import create_cpu_circuit
from cpu_isa import assemble


def build_all():
    folder = Path(__file__).with_name("assembly")
    result = []
    for source_path in sorted(folder.glob("*.asm")):
        source = source_path.read_text(encoding="utf-8")
        program = assemble(source)
        circuit = create_cpu_circuit(source)
        circuit.save(source_path.with_suffix(".json"))
        source_path.with_suffix(".bin").write_bytes(program.image)
        source_path.with_suffix(".hex").write_text(program.intel_hex(), encoding="ascii")
        result.append(source_path.stem)
    return result


if __name__ == "__main__":
    print("Built:", ", ".join(build_all()))
