"""Memory inspection and image exchange over existing component state only."""
from __future__ import annotations

from copy import deepcopy

from cpu_board import parse_intel_hex
from engine import memory_geometry


def memory_words(component):
    if component.kind == "ROM":
        return dict(component.params.get("contents", {}))
    if component.kind == "RAM":
        return dict(component.state.get("memory", component.params.get("init", {})))
    raise ValueError("Choose a RAM or ROM component")


def memory_word(component, address):
    _, _, depth = memory_geometry(component)
    if type(address) is not int or not 0 <= address < depth:
        raise ValueError(f"Address must be between 0 and {depth - 1}")
    return memory_words(component).get(str(address), 0)


def set_memory_word(component, address, value):
    _, width, depth = memory_geometry(component)
    if type(address) is not int or not 0 <= address < depth:
        raise ValueError(f"Address must be between 0 and {depth - 1}")
    if type(value) is not int or not 0 <= value < (1 << width):
        raise ValueError(f"Value must fit {width} data bits")
    if component.kind == "ROM":
        contents = dict(component.params.get("contents", {}))
        contents[str(address)] = value
        component.params["contents"] = contents
    elif component.kind == "RAM":
        words = memory_words(component)
        previous = words.get(str(address), 0)
        words[str(address)] = value
        component.state["memory"] = words
        component.state["last_write"] = {"address": address, "previous": previous,
                                         "current": value, "enabled": "inspector"}
    else:
        raise ValueError("Choose a RAM or ROM component")


def load_memory_image(component, data, kind):
    _, width, depth = memory_geometry(component)
    if width > 8: raise ValueError("BIN/Intel HEX images require memory data width of at most 8 bits")
    if kind == "bin":
        if not isinstance(data, bytes): raise ValueError("BIN image must contain bytes")
        image = data
    elif kind == "hex":
        if not isinstance(data, str): raise ValueError("Intel HEX image must be UTF-8 text")
        image = parse_intel_hex(data)
    else: raise ValueError("Choose BIN or Intel HEX")
    if len(image) > depth or any(value >= (1 << width) for value in image):
        raise ValueError(f"Image exceeds depth {depth} or {width}-bit data width")
    for address, value in enumerate(image):
        set_memory_word(component, address, value)
    return len(image)


def _hex_record(address, data, kind=0):
    payload = bytes((len(data), address >> 8, address & 255, kind)) + data
    checksum = (-sum(payload)) & 255
    return ":" + (payload + bytes((checksum,))).hex().upper()


def export_memory_image(component, kind):
    _, width, depth = memory_geometry(component)
    if width > 8: raise ValueError("BIN/Intel HEX images require memory data width of at most 8 bits")
    values = [memory_word(component, address) for address in range(depth)]
    if any(value is None for value in values):
        raise ValueError("Cannot export memory image while a word is X")
    image = bytes(values)
    if kind == "bin": return image
    if kind == "hex":
        return "\n".join([_hex_record(address, image[address:address + 16])
                          for address in range(0, len(image), 16)] + [_hex_record(0, b"", 1)]) + "\n"
    raise ValueError("Choose BIN or Intel HEX")


def memory_changes(history, component_id, branch_id=None):
    """Read retained Time Travel snapshots; no separate memory history is stored."""
    branch = history.branches.get(branch_id or history.active_branch)
    if branch is None: return []
    def words_at(uid):
        snapshot = history.snapshots.get(uid)
        if snapshot is None or component_id not in snapshot.states: return None
        params = snapshot.params[component_id]
        words = snapshot.states[component_id].get("memory", params.get("init", {}))
        if "contents" in params: words = params["contents"]
        return deepcopy(words)

    changes, previous = [], None
    if branch.parent is not None:
        parent = history.branches.get(branch.parent)
        if parent is not None:
            prior_uid = parent.states.get(branch.fork_step)
            if prior_uid: previous = words_at(prior_uid)
    for step, uid in branch.states.items():
        words = words_at(uid)
        if words is None: continue
        if previous is not None:
            for address in sorted(set(previous) | set(words), key=lambda value: int(value)):
                if previous.get(address, 0) != words.get(address, 0):
                    changes.append({"step": step, "address": int(address),
                                    "before": previous.get(address, 0), "after": words.get(address, 0)})
        previous = words
    return changes
