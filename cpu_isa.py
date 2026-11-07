"""LogicSpace 8-bit ISA and deterministic, data-only two-pass assembler.

This module produces ROM bytes. It never executes instructions; the wired
LogicSpace components and Simulator do that work.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


ROM_SIZE = 256
REGISTER_COUNT = 4
STACK_START = 0xC0
STACK_END = 0xFF


@dataclass(frozen=True)
class Instruction:
    opcode: int
    mnemonic: str
    operands: tuple[str, ...] = ()  # r: R0-R3, v: unsigned byte

    @property
    def size(self):
        return 1 + len(self.operands)


INSTRUCTIONS = (
    Instruction(0x00, "NOP"), Instruction(0x01, "HLT"),
    Instruction(0x10, "MOV", ("r", "v")), Instruction(0x11, "MOV", ("r", "r")),
    Instruction(0x12, "LOAD", ("r", "v")), Instruction(0x13, "STORE", ("r", "v")),
    Instruction(0x20, "ADD", ("r", "r")), Instruction(0x21, "SUB", ("r", "r")),
    Instruction(0x22, "AND", ("r", "r")), Instruction(0x23, "OR", ("r", "r")),
    Instruction(0x24, "XOR", ("r", "r")), Instruction(0x25, "NOT", ("r",)),
    Instruction(0x26, "SHL", ("r",)), Instruction(0x27, "SHR", ("r",)),
    Instruction(0x28, "CMP", ("r", "r")),
    Instruction(0x30, "JMP", ("v",)), Instruction(0x31, "JZ", ("v",)),
    Instruction(0x32, "JNZ", ("v",)), Instruction(0x33, "JC", ("v",)),
    Instruction(0x34, "JNC", ("v",)), Instruction(0x35, "CALL", ("v",)),
    Instruction(0x36, "RET"), Instruction(0x40, "PUSH", ("r",)),
    Instruction(0x41, "POP", ("r",)),
)
BY_OPCODE = {instruction.opcode: instruction for instruction in INSTRUCTIONS}
BY_MNEMONIC = {}
for _instruction in INSTRUCTIONS:
    BY_MNEMONIC.setdefault(_instruction.mnemonic, []).append(_instruction)


class AssemblyError(ValueError):
    def __init__(self, line, message):
        self.line = line
        self.message = message
        super().__init__(f"Line {line}: {message}")


@dataclass(frozen=True)
class ListingLine:
    line: int
    address: int
    data: bytes
    source: str


@dataclass(frozen=True)
class AssemblyResult:
    image: bytes  # The complete 256-byte ROM image, including zero-filled holes.
    listing: tuple[ListingLine, ...]
    symbols: dict[str, int]
    address_to_line: dict[int, int]
    used_addresses: frozenset[int]

    def intel_hex(self):
        records = []
        addresses = sorted(self.used_addresses)
        start = 0
        while start < len(addresses):
            chunk = [addresses[start]]
            start += 1
            while (start < len(addresses) and addresses[start] == chunk[-1] + 1
                   and len(chunk) < 16):
                chunk.append(addresses[start]); start += 1
            address = chunk[0]
            data = bytes(self.image[index] for index in chunk)
            payload = bytes((len(data), address >> 8, address & 0xFF, 0)) + data
            checksum = (-sum(payload)) & 0xFF
            records.append(":" + payload.hex().upper() + f"{checksum:02X}")
        records.append(":00000001FF")
        return "\n".join(records) + "\n"

    def listing_text(self):
        return "\n".join(f"{entry.address:02X}  {entry.data.hex(' ').upper():<9} "
                         f"{entry.line:>3}  {entry.source}" for entry in self.listing) + "\n"


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LABEL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")
_REGISTER = re.compile(r"^R([0-3])$", re.IGNORECASE)
_NUMBER = re.compile(r"^(?:0[xX][0-9a-fA-F]+|0[bB][01]+|[0-9]+)$")
_EXPRESSION = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*|0[xX][0-9a-fA-F]+|0[bB][01]+|[0-9]+)"
                         r"(?:\s*([+-])\s*([A-Za-z_][A-Za-z0-9_]*|0[xX][0-9a-fA-F]+|0[bB][01]+|[0-9]+))?\s*$")


def _split_operands(text, line):
    if not text.strip(): return ()
    parts = tuple(part.strip() for part in text.split(","))
    if any(not part for part in parts):
        raise AssemblyError(line, "empty operand; separate operands with commas")
    return parts


def _literal(token):
    return int(token, 16 if token.lower().startswith("0x") else
               2 if token.lower().startswith("0b") else 10)


def _expression(text, line, lookup):
    match = _EXPRESSION.fullmatch(text)
    if not match:
        raise AssemblyError(line, f"invalid expression {text!r}")
    def term(token):
        if _NUMBER.fullmatch(token): return _literal(token)
        return lookup(token.upper(), line)
    value = term(match.group(1))
    if match.group(2):
        offset = term(match.group(3))
        value += offset if match.group(2) == "+" else -offset
    return value


def _parse_instruction(text, line):
    fields = text.split(None, 1)
    mnemonic, rest = fields[0], fields[1] if len(fields) > 1 else ""
    mnemonic = mnemonic.upper()
    operands = _split_operands(rest, line)
    for operand in operands:
        if re.fullmatch(r"R[0-9]+", operand, re.IGNORECASE) and not _REGISTER.fullmatch(operand):
            raise AssemblyError(line, f"invalid register {operand}; use R0–R3")
    candidates = BY_MNEMONIC.get(mnemonic)
    if not candidates:
        raise AssemblyError(line, f"unknown instruction {mnemonic}")
    for spec in candidates:
        if len(operands) != len(spec.operands): continue
        if all(bool(_REGISTER.fullmatch(operand)) == (kind == "r")
               for operand, kind in zip(operands, spec.operands)):
            return spec, operands
    forms = " or ".join(f"{mnemonic} " + ", ".join("R0–R3" if kind == "r" else "byte/address"
                                                    for kind in spec.operands)
                        for spec in candidates)
    raise AssemblyError(line, f"invalid operands; expected {forms.strip()}")


def assemble(source: str) -> AssemblyResult:
    if not isinstance(source, str):
        raise TypeError("Assembly source must be text")
    labels = {}
    constants = {}
    statements = []
    cursor = 0
    for line_no, original in enumerate(source.splitlines(), 1):
        text = original.split(";", 1)[0].strip()
        if not text: continue
        while match := _LABEL.match(text):
            name = match.group(1).upper()
            if name in labels or name in constants:
                raise AssemblyError(line_no, f"duplicate symbol {name}")
            labels[name] = cursor
            text = text[match.end():].strip()
        if not text: continue
        fields = text.split(None, 1)
        keyword, rest = fields[0], fields[1] if len(fields) > 1 else ""
        keyword = keyword.upper()
        if keyword == ".EQU":
            parts = _split_operands(rest, line_no)
            if len(parts) != 2 or not _IDENTIFIER.fullmatch(parts[0]):
                raise AssemblyError(line_no, "use .EQU NAME, value")
            name = parts[0].upper()
            if name in labels or name in constants:
                raise AssemblyError(line_no, f"duplicate symbol {name}")
            constants[name] = (parts[1], line_no)
            continue
        if keyword == ".ORG":
            def known(name, line, visiting=()):
                if name in labels: return labels[name]
                if name in constants:
                    if name in visiting:
                        raise AssemblyError(line, f"circular constant {name}")
                    value, _ = constants[name]
                    return _expression(value, line,
                                       lambda token, current: known(token, current, visiting + (name,)))
                raise AssemblyError(line, f".ORG needs a previously defined symbol: {name}")
            cursor = _expression(rest, line_no, known)
            if not 0 <= cursor < ROM_SIZE:
                raise AssemblyError(line_no, ".ORG address must be 0–255")
            continue
        if keyword in (".BYTE", ".WORD"):
            args = _split_operands(rest, line_no)
            if not args: raise AssemblyError(line_no, f"{keyword} needs values")
            size = len(args) * (2 if keyword == ".WORD" else 1)
            statements.append((line_no, cursor, keyword, args, original))
        else:
            spec, args = _parse_instruction(text, line_no)
            size = spec.size
            statements.append((line_no, cursor, spec, args, original))
        if cursor + size > ROM_SIZE:
            raise AssemblyError(line_no, "program exceeds 256-byte ROM")
        cursor += size

    def resolve(name, line, visiting=()):
        if name in labels: return labels[name]
        if name not in constants: raise AssemblyError(line, f"undefined symbol {name}")
        if name in visiting: raise AssemblyError(line, f"circular constant {name}")
        expression, definition_line = constants[name]
        return _expression(expression, definition_line,
                           lambda token, current: resolve(token, current, visiting + (name,)))

    symbols = {**labels, **{name: resolve(name, line) for name, (_, line) in constants.items()}}
    image = bytearray(ROM_SIZE)
    occupied = set()
    listing = []
    source_map = {}
    for line, address, operation, args, original in statements:
        encoded = bytearray()
        if operation == ".BYTE" or operation == ".WORD":
            for expression in args:
                value = _expression(expression, line, resolve)
                maximum = 65535 if operation == ".WORD" else 255
                if not 0 <= value <= maximum:
                    raise AssemblyError(line, f"{operation} value must be 0–{maximum}")
                encoded.append(value & 0xFF)
                if operation == ".WORD": encoded.append(value >> 8)
        else:
            encoded.append(operation.opcode)
            for kind, operand in zip(operation.operands, args):
                if kind == "r":
                    encoded.append(int(_REGISTER.fullmatch(operand).group(1)))
                else:
                    value = _expression(operand, line, resolve)
                    if not 0 <= value <= 255:
                        raise AssemblyError(line, f"operand {operand!r} must fit in 8 bits")
                    encoded.append(value)
        for offset, value in enumerate(encoded):
            target = address + offset
            if target in occupied:
                raise AssemblyError(line, f"ROM address 0x{target:02X} is already used")
            occupied.add(target)
            image[target] = value
            source_map[target] = line
        listing.append(ListingLine(line, address, bytes(encoded), original.rstrip()))
    return AssemblyResult(bytes(image), tuple(listing), symbols, source_map, frozenset(occupied))


def decode(image: bytes, address: int):
    if not 0 <= address < len(image): raise ValueError("Instruction address outside ROM image")
    opcode = image[address]
    spec = BY_OPCODE.get(opcode)
    if spec is None: return f".BYTE 0x{opcode:02X}  ; invalid opcode"
    if address + spec.size > len(image): return f"{spec.mnemonic}  ; truncated instruction"
    operands = []
    for kind, value in zip(spec.operands, image[address + 1:address + spec.size]):
        operands.append(f"R{value}" if kind == "r" else f"0x{value:02X}")
    return spec.mnemonic + (" " + ", ".join(operands) if operands else "")
