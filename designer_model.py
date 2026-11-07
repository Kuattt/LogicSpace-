"""Editable custom-block document backed by the existing Circuit and Simulator."""
from __future__ import annotations

from copy import deepcopy
import re

from component_library import block_definition_from_circuit, validate_definition
from engine import Circuit, Simulator, bit_width, pins

SIDES = ("LEFT", "RIGHT", "TOP", "BOTTOM")
DEFAULT_APPEARANCE = {"body_color": "#29465a", "width": 180, "height": 120,
                      "label": "", "short_description": ""}


class DesignerModel:
    def __init__(self, circuit=None, *, name="New Component", description="", category="Custom",
                 appearance=None, library_id=None, version=0):
        self.circuit = circuit or Circuit()
        self.name = name
        self.description = description
        self.category = category
        self.appearance = {**DEFAULT_APPEARANCE, **(appearance or {})}
        self.library_id = library_id
        self.version = version
        self.ensure_terminal_metadata()

    def ensure_terminal_metadata(self):
        counts = {"INPUT": 0, "OUTPUT": 0}
        for component in self.circuit.components.values():
            if component.kind in counts:
                component.params.setdefault("label", f"{'IN' if component.kind == 'INPUT' else 'OUT'}{counts[component.kind] + 1}")
                component.params.setdefault("_terminal", {"side": "LEFT" if component.kind == "INPUT" else "RIGHT",
                                                           "order": counts[component.kind], "description": ""})
                counts[component.kind] += 1

    @classmethod
    def from_definition(cls, definition, name, *, description="", category="Custom", library_id=None, version=0):
        validate_definition(definition, name)
        circuit = Circuit.from_dict(deepcopy(definition["circuit"]))
        design = definition.get("designer", {})
        for mapping in (definition["input_map"], definition["output_map"]):
            for external, target in mapping.items():
                cid = target if isinstance(target, str) else target[0]
                suffix = target[1][1:] if isinstance(target, list) else ""
                label = external[:-len(suffix)] if suffix and external.endswith(suffix) else external
                circuit.components[cid].params.setdefault("label", label)
        for component in circuit.components.values():
            if component.kind in ("INPUT", "OUTPUT") and "_terminal" not in component.params:
                component.params["_terminal"] = {"side": "LEFT" if component.kind == "INPUT" else "RIGHT",
                                                 "order": len([c for c in circuit.components.values()
                                                               if c.kind == component.kind and c.id < component.id]),
                                                 "description": ""}
        return cls(circuit, name=name, description=description, category=category,
                   appearance=design.get("appearance"), library_id=library_id, version=version)

    def terminals(self):
        return [component for component in self.circuit.components.values() if component.kind in ("INPUT", "OUTPUT")]

    def add_terminal(self, name, direction, width=1, side=None, description=""):
        self._validate_terminal_name(name)
        if direction not in ("INPUT", "OUTPUT") or not isinstance(width, int) or not 1 <= width <= 8:
            raise ValueError("Terminal direction must be INPUT or OUTPUT, with 1–8 bits")
        side = side or ("LEFT" if direction == "INPUT" else "RIGHT")
        if side not in SIDES:
            raise ValueError("Choose LEFT, RIGHT, TOP or BOTTOM")
        same = [c for c in self.terminals() if c.kind == direction]
        component = self.circuit.add(direction, -300 if direction == "INPUT" else 220,
                                     len(same) * 110,
                                     {"label": name, "width": width,
                                      "_terminal": {"side": side, "order": len(same), "description": description}})
        return component

    def remove_terminal(self, component_id):
        self._terminal(component_id)
        self.circuit.remove(component_id)

    def configure_terminal(self, component_id, *, name=None, width=None, side=None, order=None, description=None):
        component = self._terminal(component_id)
        updated = deepcopy(component.params)
        if name is not None and name != component.params.get("label"):
            self._validate_terminal_name(name, component_id)
            updated["label"] = name
        if width is not None:
            if not isinstance(width, int) or not 1 <= width <= 8:
                raise ValueError("Terminal width must be 1–8 bits")
            updated["width"] = width
        metadata = updated.setdefault("_terminal", {})
        if side is not None:
            if side not in SIDES:
                raise ValueError("Choose LEFT, RIGHT, TOP or BOTTOM")
            metadata["side"] = side
        if order is not None:
            if not isinstance(order, int) or order < 0:
                raise ValueError("Terminal order must be zero or greater")
            metadata["order"] = order
        if description is not None:
            metadata["description"] = str(description)
        tentative = deepcopy(component)
        tentative.params = updated
        valid = pins(tentative, self.circuit.blocks)[1 if component.kind == "INPUT" else 0]
        changes = []
        for wire in self.circuit.wires.values():
            if component.kind == "INPUT" and wire.source == component_id:
                mapped = wire.source_pin if wire.source_pin in valid else wire.source_pin + "0" if wire.source_pin == "Q" and "Q0" in valid else "Q" if wire.source_pin == "Q0" and "Q" in valid else None
                if mapped is None:
                    raise ValueError("Disconnect wires from removed bits before reducing terminal width")
                changes.append((wire, "source_pin", mapped))
            elif component.kind == "OUTPUT" and wire.target == component_id:
                mapped = wire.target_pin if wire.target_pin in valid else wire.target_pin + "0" if wire.target_pin == "A" and "A0" in valid else "A" if wire.target_pin == "A0" and "A" in valid else None
                if mapped is None:
                    raise ValueError("Disconnect wires from removed bits before reducing terminal width")
                changes.append((wire, "target_pin", mapped))
        component.params = updated
        for wire, key, value in changes:
            setattr(wire, key, value)
        return component

    def _terminal(self, component_id):
        component = self.circuit.components.get(component_id)
        if component is None or component.kind not in ("INPUT", "OUTPUT"):
            raise ValueError("Choose an INPUT or OUTPUT terminal")
        return component

    def _validate_terminal_name(self, name, exclude=None):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise ValueError("Terminal name must start with a letter and contain only letters, digits or _")
        if any(c.id != exclude and c.params.get("label") == name for c in self.terminals()):
            raise ValueError("Terminal names must be unique")

    def validate(self):
        if not self.name.strip():
            raise ValueError("Enter a component name")
        if not self.category.strip():
            raise ValueError("Choose a category")
        color = self.appearance.get("body_color", "")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Body color must be a six-digit hex color")
        for key in ("width", "height"):
            value = self.appearance.get(key)
            if not isinstance(value, int) or not 100 <= value <= 520:
                raise ValueError(f"Body {key} must be 100–520")
        if not isinstance(self.description, str) or not isinstance(self.appearance.get("label"), str):
            raise ValueError("Description and label must be text")
        terminals = self.terminals()
        if not any(c.kind == "INPUT" for c in terminals) or not any(c.kind == "OUTPUT" for c in terminals):
            raise ValueError("Add at least one INPUT and one OUTPUT terminal")
        external_names = set()
        for component in terminals:
            self._validate_terminal_name(component.params.get("label"), component.id)
            meta = component.params.get("_terminal", {})
            if meta.get("side") not in SIDES or not isinstance(meta.get("order"), int) or meta["order"] < 0:
                raise ValueError("Set a valid side and order for every terminal")
            if not 1 <= bit_width(component) <= 8:
                raise ValueError("Terminal width must be 1–8 bits")
            for bit in range(bit_width(component)):
                external = (component.params["label"] if bit_width(component) == 1
                            else f"{component.params['label']}{bit}")
                if external in external_names:
                    raise ValueError(f"External pin name {external} is used twice; rename a terminal")
                external_names.add(external)
        if self.circuit.validate():
            raise ValueError("Fix internal wiring: " + "; ".join(self.circuit.validate()))
        # Every external output bit needs a real internal driver.
        for component in terminals:
            if component.kind == "OUTPUT":
                inputs = pins(component, self.circuit.blocks)[0]
                for pin in inputs:
                    if not any(w.target == component.id and w.target_pin == pin for w in self.circuit.wires.values()):
                        raise ValueError(f"Connect external output {component.params['label']}.{pin} to the internal circuit")
        return self.definition()

    def definition(self):
        definition = block_definition_from_circuit(self.circuit)
        definition["designer"] = self.preview_spec()["designer"]
        return validate_definition(definition, self.name)

    def preview_spec(self):
        layout = {}
        inputs, outputs = [], []
        for component in self.terminals():
            meta = component.params.get("_terminal", {})
            names = pins(component, self.circuit.blocks)[1 if component.kind == "INPUT" else 0]
            label = component.params.get("label", "")
            for bit, pin in enumerate(names):
                external = label if len(names) == 1 else label + str(bit)
                (inputs if component.kind == "INPUT" else outputs).append(external)
                layout[external] = {"side": meta.get("side", "LEFT" if component.kind == "INPUT" else "RIGHT"),
                                    "order": int(meta.get("order", 0)) * 8 + bit,
                                    "description": str(meta.get("description", ""))}
        return {"inputs": inputs, "outputs": outputs,
                "designer": {"appearance": deepcopy(self.appearance), "terminals": layout}}

    def test(self, values, steps=0):
        definition = self.validate()
        circuit = Circuit.from_dict(deepcopy(definition["circuit"]))
        circuit.tick = 0
        for component in circuit.components.values():
            component.state.clear()
        for external, target in definition["input_map"].items():
            value = values.get(external)
            if value not in (0, 1, None):
                raise ValueError(f"Input {external} must be 0, 1 or X")
            if isinstance(target, str):
                circuit.components[target].params["value"] = value
            else:
                cid, pin = target
                bits = circuit.components[cid].params.setdefault("_bit_values", [None] * bit_width(circuit.components[cid]))
                bits[int(pin[1:])] = value
        simulator = Simulator(circuit)
        for _ in range(max(0, int(steps))):
            simulator.step()
        if simulator.errors:
            raise ValueError("Simulation error: " + "; ".join(simulator.errors))
        outputs = {}
        for external, target in definition["output_map"].items():
            cid, pin = (target, "A") if isinstance(target, str) else target
            outputs[external] = simulator.inputs.get(cid, {}).get(pin)
        return outputs
