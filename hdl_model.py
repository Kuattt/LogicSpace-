"""A deliberately small, checked Verilog-to-LogicSpace bridge.

Only the syntax accepted by Parser is claimed as supported. Every imported
operation is compiled to ordinary Circuit components and connections.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from uuid import uuid4

from component_library import block_definition_from_circuit
from engine import BUS_WIDTHS, SEQUENTIAL, Circuit, Simulator, bus_ports, pins, wire_bit_pairs


class HDLError(ValueError):
    def __init__(self, message, line=1, column=1):
        self.line, self.column = line, column
        super().__init__(f"{line}:{column}: {message}")


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    category: str
    file: str
    line: int
    column: int
    message: str
    fix: str

    def __str__(self):
        return (f"{self.file}:{self.line}:{self.column}: {self.severity} "
                f"[{self.category}]: {self.message} Fix: {self.fix}")


@dataclass(frozen=True)
class Token:
    text: str
    line: int
    column: int


@dataclass(frozen=True)
class Expr:
    kind: str
    value: object
    token: Token
    left: "Expr | None" = None
    right: "Expr | None" = None


@dataclass
class Module:
    name: str
    token: Token
    header: list[str] = field(default_factory=list)
    signals: dict[str, tuple[str, int]] = field(default_factory=dict)
    assignments: list[tuple[str, Expr, Token]] = field(default_factory=list)
    instances: list[tuple[str, str, dict[str, Expr], Token]] = field(default_factory=list)
    procedures: list["Procedure"] = field(default_factory=list)
    memories: dict[str, tuple[int, int, Token]] = field(default_factory=dict)
    initial_memory: list["ProcAssign"] = field(default_factory=list)


@dataclass(frozen=True)
class ProcAssign:
    target: object
    expr: Expr
    nonblocking: bool
    token: Token


@dataclass(frozen=True)
class ProcIf:
    condition: Expr
    yes: object
    no: object | None
    token: Token


@dataclass(frozen=True)
class ProcBlock:
    statements: tuple
    token: Token


@dataclass(frozen=True)
class ProcCase:
    selector: Expr
    arms: tuple[tuple[Expr, object], ...]
    default: object | None
    token: Token


@dataclass(frozen=True)
class Procedure:
    kind: str
    clock: str | None
    edge: str | None
    body: object
    token: Token
    reset: str | None = None
    reset_edge: str | None = None


_TOKEN = re.compile(r"\s+|//[^\n]*|/\*[\s\S]*?\*/|\d+'[bBhHdD][0-9a-fA-F_xXzZ]+|\d+|[A-Za-z_][A-Za-z_0-9$]*|&&|\|\||===|==|!=|<=|>=|[()\[\]{},;:.=+\-*/&|^~!?@]")
_PREC = {"||": 1, "&&": 2, "===": 2, "|": 3, "^": 4, "&": 5,
         "+": 6, "-": 6, "*": 7, "/": 7}
_KEYWORDS = {"module", "endmodule", "input", "output", "wire", "logic", "assign",
             "always", "always_comb", "always_ff", "initial", "reg", "parameter",
             "generate", "endgenerate", "begin", "end", "if", "else", "case",
             "default", "endcase", "posedge", "negedge"}


def tokenize(source):
    tokens, pos, line, col = [], 0, 1, 1
    while pos < len(source):
        match = _TOKEN.match(source, pos)
        if not match:
            raise HDLError(f"Unsupported character {source[pos]!r}", line, col)
        raw = match.group()
        if not raw.isspace() and not raw.startswith(("//", "/*")):
            tokens.append(Token(raw, line, col))
        pos = match.end()
        if "\n" in raw:
            line += raw.count("\n"); col = len(raw.rsplit("\n", 1)[-1]) + 1
        else:
            col += len(raw)
    tokens.append(Token("<eof>", line, col))
    return tokens


class Parser:
    def __init__(self, source):
        self.tokens, self.at = tokenize(source), 0

    @property
    def here(self): return self.tokens[self.at]

    def take(self, expected=None):
        token = self.here
        if expected is not None and token.text != expected:
            raise HDLError(f"Expected {expected!r}, got {token.text!r}", token.line, token.column)
        self.at += 1
        return token

    def accept(self, text):
        if self.here.text == text:
            self.at += 1; return True
        return False

    def identifier(self):
        token = self.here
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9$]*", token.text) or token.text in _KEYWORDS:
            raise HDLError("Expected identifier", token.line, token.column)
        return self.take()

    def width(self):
        if not self.accept("["): return 1
        high = self.take(); self.take(":"); low = self.take(); self.take("]")
        if not high.text.isdigit() or low.text != "0" or int(high.text) + 1 not in (2, 4, 8, 16, 32):
            raise HDLError("Only [N:0] widths 2, 4, 8, 16, 32 are supported", high.line, high.column)
        return int(high.text) + 1

    def declaration(self, module, direction, until_semicolon=True):
        if self.here.text in ("wire", "logic"): self.take()
        width = self.width()
        while True:
            name = self.identifier()
            if name.text in module.signals or name.text in module.memories:
                raise HDLError(f"Duplicate signal {name.text}", name.line, name.column)
            if self.accept("["):
                if direction not in ("wire", "logic", "reg"):
                    raise HDLError("Memory arrays need wire, logic or reg declaration", name.line, name.column)
                low = self.take(); self.take(":"); high = self.take(); self.take("]")
                if low.text != "0" or not high.text.isdigit() or not 1 <= int(high.text) < 256:
                    raise HDLError("Memory range must be [0:N], N from 1 to 255", low.line, low.column)
                module.memories[name.text] = (width, int(high.text) + 1, name)
            else:
                module.signals[name.text] = (direction, width)
            if not self.accept(","): break
            if self.here.text in _KEYWORDS:
                raise HDLError("Expected another signal name after comma", self.here.line, self.here.column)
        if until_semicolon: self.take(";")

    def expression(self, minimum=0):
        token = self.take()
        if token.text in ("~", "!", "|"):
            if token.text == "|":
                left = Expr("reduction_or", None, token, self.expression(8))
            else:
                left = Expr("unary", token.text, token, self.expression(8))
        elif token.text == "(":
            left = self.expression(); self.take(")")
        elif token.text == "{":
            parts = [self.expression()]
            while self.accept(","):
                parts.append(self.expression())
            self.take("}")
            left = Expr("concat", tuple(parts), token)
        elif re.fullmatch(r"\d+(?:'[bBhHdD][0-9a-fA-F_xXzZ]+)?", token.text):
            left = Expr("literal", token.text, token)
        elif re.fullmatch(r"[A-Za-z_][A-Za-z_0-9$]*", token.text):
            left = Expr("name", token.text, token)
            if self.accept("["):
                if token.text in self.current_module.memories:
                    index = self.expression(); self.take("]")
                    left = Expr("memory_read", token.text, token, index)
                else:
                    index = self.take(); self.take("]")
                    if not index.text.isdigit():
                        raise HDLError("Bit select needs a constant index", index.line, index.column)
                    left = Expr("bit", (token.text, int(index.text)), token)
        else:
            raise HDLError(f"Unsupported expression near {token.text!r}", token.line, token.column)
        while self.here.text in _PREC and _PREC[self.here.text] >= minimum:
            op = self.take()
            right = self.expression(_PREC[op.text] + 1)
            left = Expr("case_equal" if op.text == "===" else "binary", op.text, op, left, right)
        if minimum == 0 and self.here.text == "?":
            question = self.take()
            yes = self.expression(); self.take(":")
            no = self.expression()
            left = Expr("ternary", (yes, no), question, left)
        return left

    def statement(self):
        token = self.here
        if self.accept("begin"):
            statements = []
            while self.here.text != "end":
                if self.here.text == "<eof>":
                    raise HDLError("Missing end for procedural block", token.line, token.column)
                statements.append(self.statement())
            self.take("end")
            return ProcBlock(tuple(statements), token)
        if self.accept("if"):
            self.take("("); condition = self.expression(); self.take(")")
            yes = self.statement()
            no = self.statement() if self.accept("else") else None
            return ProcIf(condition, yes, no, token)
        if self.accept("case"):
            self.take("("); selector = self.expression(); self.take(")")
            arms, default = [], None
            while self.here.text != "endcase":
                if self.here.text == "<eof>":
                    raise HDLError("Missing endcase", token.line, token.column)
                if self.accept("default"):
                    if default is not None:
                        raise HDLError("Duplicate case default", self.here.line, self.here.column)
                    self.take(":"); default = self.statement()
                else:
                    label = self.expression()
                    if label.kind != "literal":
                        raise HDLError("Case labels must be constant literals", label.token.line, label.token.column)
                    self.take(":"); arms.append((label, self.statement()))
            self.take("endcase")
            if not arms:
                raise HDLError("Case needs at least one constant arm", token.line, token.column)
            return ProcCase(selector, tuple(arms), default, token)
        target = self.identifier()
        address = None
        if self.accept("["):
            if target.text in self.current_module.memories:
                address = self.expression(); self.take("]")
            elif target.text in self.current_module.signals:
                index = self.take(); self.take("]")
                if not index.text.isdigit():
                    raise HDLError("Partial vector assignment needs a constant bit index", index.line, index.column)
                address = ("bit", target.text, int(index.text))
            else:
                raise HDLError("Indexed assignment needs a declared vector or memory", target.line, target.column)
        assignment = self.take()
        if assignment.text not in ("=", "<="):
            raise HDLError("Procedural statement needs = or <=", assignment.line, assignment.column)
        expr = self.expression(); self.take(";")
        return ProcAssign((address if isinstance(address, tuple) else (target.text, address))
                          if address is not None else target.text,
                          expr, assignment.text == "<=", target)

    def procedure(self):
        token = self.take()
        if token.text == "always_comb":
            return Procedure("comb", None, None, self.statement(), token)
        if token.text not in ("always", "always_ff"):
            raise HDLError("Unsupported procedural block", token.line, token.column)
        self.take("@"); self.take("(")
        if self.accept("*"):
            if token.text == "always_ff":
                raise HDLError("always_ff needs posedge or negedge clock", token.line, token.column)
            self.take(")")
            return Procedure("comb", None, None, self.statement(), token)
        edge = self.take()
        if edge.text not in ("posedge", "negedge"):
            raise HDLError("Sensitivity list needs * or one posedge/negedge clock", edge.line, edge.column)
        clock = self.identifier()
        reset, reset_edge = None, None
        if self.here.text in ("or", ","):
            self.take()
            edge_token = self.take()
            if edge_token.text not in ("posedge", "negedge"):
                raise HDLError("Second sensitivity event must be a reset edge", edge_token.line, edge_token.column)
            reset_edge = edge_token.text
            reset = self.identifier().text
            if reset == clock.text:
                raise HDLError("Clock and asynchronous reset must be different signals",
                               edge_token.line, edge_token.column)
        self.take(")")
        return Procedure("clocked", clock.text, edge.text, self.statement(), token, reset, reset_edge)

    def parse(self):
        modules = {}
        while self.here.text != "<eof>":
            start = self.take("module")
            name = self.identifier().text
            if name in modules: raise HDLError(f"Duplicate module {name}", start.line, start.column)
            module = Module(name, start)
            self.current_module = module
            self.take("(")
            inherited_direction, inherited_width = None, 1
            while self.here.text != ")":
                if self.here.text in ("input", "output"):
                    direction = self.take().text
                    if self.here.text in ("wire", "logic"): self.take()
                    width = self.width(); port = self.identifier()
                    if port.text in module.signals:
                        raise HDLError(f"Duplicate port {port.text}", port.line, port.column)
                    module.signals[port.text] = (direction, width)
                    module.header.append(port.text)
                    inherited_direction, inherited_width = direction, width
                else:
                    port = self.identifier()
                    module.header.append(port.text)
                    if inherited_direction is not None:
                        if port.text in module.signals:
                            raise HDLError(f"Duplicate port {port.text}", port.line, port.column)
                        module.signals[port.text] = (inherited_direction, inherited_width)
                if not self.accept(","): break
            self.take(")"); self.take(";")
            while self.here.text != "endmodule":
                if self.here.text == "<eof>":
                    raise HDLError("Missing endmodule", start.line, start.column)
                if self.here.text in ("input", "output", "wire", "logic", "reg"):
                    direction = self.take().text
                    self.declaration(module, direction)
                elif self.accept("assign"):
                    lhs = self.identifier(); self.take("=")
                    expr = self.expression(); self.take(";")
                    module.assignments.append((lhs.text, expr, lhs))
                elif self.here.text in ("always", "always_comb", "always_ff"):
                    module.procedures.append(self.procedure())
                elif self.accept("initial"):
                    body = self.statement()
                    statements = body.statements if isinstance(body, ProcBlock) else (body,)
                    if not statements or any(not isinstance(item, ProcAssign) or
                                             not isinstance(item.target, tuple) or
                                             item.target[0] == "bit" or item.nonblocking
                                             for item in statements):
                        raise HDLError("Only blocking literal memory initialization is supported",
                                       start.line, start.column)
                    module.initial_memory.extend(statements)
                else:
                    type_token = self.identifier(); instance = self.identifier()
                    self.take("("); connections = {}
                    while self.here.text != ")":
                        self.take("."); port = self.identifier()
                        if port.text in connections:
                            raise HDLError(f"Duplicate port connection {port.text}", port.line, port.column)
                        self.take("("); connections[port.text] = self.expression(); self.take(")")
                        if not self.accept(","): break
                    self.take(")"); self.take(";")
                    module.instances.append((type_token.text, instance.text, connections, type_token))
            self.take("endmodule")
            if not module.header or len(set(module.header)) != len(module.header):
                raise HDLError("Module needs unique ports", start.line, start.column)
            for port in module.header:
                if port not in module.signals or module.signals[port][0] not in ("input", "output"):
                    raise HDLError(f"Port {port} has no input/output declaration", start.line, start.column)
            for signal, (direction, _) in module.signals.items():
                if direction in ("input", "output") and signal not in module.header:
                    raise HDLError(f"Port {signal} is missing from module header", start.line, start.column)
            modules[name] = module
        if not modules: raise HDLError("No module found")
        return modules


def parse(source): return Parser(source).parse()


def _literal(expr, expected=None):
    text = expr.value.replace("_", "")
    if "'" not in text:
        value = int(text)
        width = expected or max(1, value.bit_length())
        if width not in (1, *BUS_WIDTHS) or value >= 1 << width:
            raise HDLError("Literal does not fit a supported width", expr.token.line, expr.token.column)
        return width, [((value >> bit) & 1) for bit in range(width)]
    size, digits = text.split("'", 1); width = int(size)
    if width not in (1, *BUS_WIDTHS):
        raise HDLError("Literal width must be 1, 2, 4, 8, 16 or 32", expr.token.line, expr.token.column)
    base = {"b": 2, "h": 16, "d": 10}.get(digits[0].lower())
    if base is None: raise HDLError("Unsupported literal base", expr.token.line, expr.token.column)
    body = digits[1:].lower()
    if "z" in body: raise HDLError("High impedance Z is not supported", expr.token.line, expr.token.column)
    if "x" in body:
        if base != 2 or len(body) != width:
            raise HDLError("X literals require full-width binary digits", expr.token.line, expr.token.column)
        return width, [None if ch == "x" else int(ch) for ch in reversed(body)]
    try: value = int(body, base)
    except ValueError as error:
        raise HDLError("Invalid numeric literal", expr.token.line, expr.token.column) from error
    if value >= 1 << width:
        raise HDLError("Literal exceeds its declared width", expr.token.line, expr.token.column)
    return width, [(value >> bit) & 1 for bit in range(width)]


def _pin_vector(component, prefix, width):
    return [(component.id, prefix if width == 1 else f"{prefix}{i}") for i in range(width)]


def _connect_vector(circuit, sources, targets):
    if len(sources) != len(targets): raise ValueError("Internal HDL width mismatch")
    if len(sources) in BUS_WIDTHS and len({cid for cid, _ in sources}) == 1 and len({cid for cid, _ in targets}) == 1:
        sid, tid = sources[0][0], targets[0][0]
        for sport, sbits in bus_ports(circuit.components[sid], circuit.blocks)["output"].items():
            if list(sbits) != [pin for _, pin in sources]: continue
            for tport, tbits in bus_ports(circuit.components[tid], circuit.blocks)["input"].items():
                if list(tbits) == [pin for _, pin in targets]:
                    circuit.connect_bus(sid, sport, tid, tport); return
    for (sid, spin), (tid, tpin) in zip(sources, targets):
        circuit.connect(sid, spin, tid, tpin)


def _replace_expr(expr, values):
    """Inline earlier blocking assignments; clocked NBAs never use this path."""
    if expr.kind == "name" and expr.value in values:
        return values[expr.value]
    if expr.kind == "bit" and expr.value[0] in values:
        raise HDLError("Bit selection of a procedurally assigned temporary is unsupported",
                       expr.token.line, expr.token.column)
    if expr.kind == "ternary":
        return Expr("ternary", tuple(_replace_expr(part, values) for part in expr.value),
                    expr.token, _replace_expr(expr.left, values))
    if expr.kind in ("unary", "binary", "replace_bit"):
        return Expr(expr.kind, expr.value, expr.token,
                    _replace_expr(expr.left, values),
                    _replace_expr(expr.right, values) if expr.right else None)
    return expr


def _procedural_values(statement, incoming, clocked):
    """Convert supported procedural control flow to next-state expressions."""
    if isinstance(statement, ProcBlock):
        values = dict(incoming)
        for child in statement.statements:
            values = _procedural_values(child, values, clocked)
        return values
    if isinstance(statement, ProcAssign):
        if clocked and not statement.nonblocking:
            raise HDLError("Clocked assignments must use <= to avoid ordering races",
                           statement.token.line, statement.token.column)
        if not clocked and statement.nonblocking:
            raise HDLError("Combinational assignments must use =",
                           statement.token.line, statement.token.column)
        values = dict(incoming)
        if isinstance(statement.target, tuple) and statement.target[0] == "bit":
            _, name, index = statement.target
            base = incoming.get(name)
            if base is None:
                if not clocked:
                    raise HDLError(f"Latch inferred for {name}: assign the full vector first",
                                   statement.token.line, statement.token.column)
                base = Expr("name", name, statement.token)
            part = statement.expr if clocked else _replace_expr(statement.expr, incoming)
            values[name] = Expr("replace_bit", index, statement.token, base, part)
        else:
            values[statement.target] = statement.expr if clocked else _replace_expr(statement.expr, incoming)
        return values
    if isinstance(statement, ProcIf):
        raw = statement.condition if clocked else _replace_expr(statement.condition, incoming)
        condition = Expr("truth", None, statement.token, raw)
        yes = _procedural_values(statement.yes, incoming, clocked)
        no = _procedural_values(statement.no, incoming, clocked) if statement.no else dict(incoming)
        result = dict(incoming)
        for target in set(yes) | set(no):
            left = yes.get(target)
            right = no.get(target)
            if left is None or right is None:
                if not clocked:
                    raise HDLError(f"Latch inferred for {target}: assign it on every branch",
                                   statement.token.line, statement.token.column)
                hold = Expr("name", target, statement.token)
                left = left or hold; right = right or hold
            result[target] = Expr("ternary", (left, right), statement.token, condition)
        return result
    if isinstance(statement, ProcCase):
        if statement.default is None and not clocked:
            raise HDLError("Latch inferred from case without default: add default assignment",
                           statement.token.line, statement.token.column)
        base = (_procedural_values(statement.default, incoming, clocked)
                if statement.default else dict(incoming))
        result = dict(base)
        seen = set()
        for label, body in reversed(statement.arms):
            if label.value in seen:
                raise HDLError(f"Duplicate case label {label.value}", label.token.line, label.token.column)
            seen.add(label.value)
            values = _procedural_values(body, incoming, clocked)
            raw_selector = statement.selector if clocked else _replace_expr(statement.selector, incoming)
            condition = Expr("case_match", label, label.token, raw_selector)
            for target in set(result) | set(values):
                yes = values.get(target)
                no = result.get(target)
                if yes is None or no is None:
                    if not clocked:
                        raise HDLError(f"Latch inferred for {target}: assign it in every case arm",
                                       statement.token.line, statement.token.column)
                    hold = Expr("name", target, statement.token)
                    yes = yes or hold; no = no or hold
                result[target] = Expr("ternary", (yes, no), statement.token, condition)
        return result
    raise HDLError("Unsupported procedural statement")


class _Builder:
    def __init__(self, module, definitions, modules, nested, clock_generators=False):
        self.module, self.definitions, self.modules, self.nested = module, definitions, modules, nested
        self.clock_generators = clock_generators
        self.clock_names = {item.clock for item in module.procedures if item.kind == "clocked"}
        self.reset_defaults = {item.reset: 0 if item.reset_edge == "posedge" else 1
                               for item in module.procedures if item.reset}
        self.circuit = Circuit(); self.circuit.blocks = deepcopy(definitions)
        self.sources, self.drivers, self.resolving = {}, {}, set()
        self.terminal_targets = {}
        self.instance_inputs = []
        self.sequential_inputs = []
        self.memory_components = {}
        self.memory_addresses = {}
        self.memory_writers = set()
        self.next_x = 0

    def _memory_initial(self, name):
        width, depth, _ = self.module.memories[name]
        result = {}
        for statement in self.module.initial_memory:
            if statement.target[0] != name: continue
            index, value = statement.target[1], statement.expr
            if index.kind != "literal" or value.kind != "literal":
                raise HDLError("Memory initialization needs literal address and value",
                               statement.token.line, statement.token.column)
            _, address_bits = _literal(index)
            value_width, value_bits = _literal(value, width)
            address = None if None in address_bits else sum(bit << i for i, bit in enumerate(address_bits))
            if address is None or address >= depth or value_width != width or None in value_bits:
                raise HDLError("Memory initialization address/value is out of range or X",
                               statement.token.line, statement.token.column)
            result[str(address)] = sum(bit << i for i, bit in enumerate(value_bits))
        return result

    def _memory_component(self, name):
        if name not in self.memory_components:
            width, depth, _ = self.module.memories[name]
            address_bits = max(1, (depth - 1).bit_length())
            writable = name in self.memory_writers
            settings = {"init" if writable else "contents": self._memory_initial(name)}
            component = self.add("RAM" if writable else "ROM", width,
                                 address_bits=address_bits, data_bits=width, depth=depth,
                                 read_mode="async", label=name, **settings)
            self.memory_components[name] = component
        return self.memory_components[name]

    def _memory_address(self, name, index):
        width, depth, _ = self.module.memories[name]
        address_bits = max(1, (depth - 1).bit_length())
        if index.kind != "name" or index.value not in self.module.signals:
            raise HDLError("Memory address must be one declared signal", index.token.line, index.token.column)
        if self.module.signals[index.value][1] != address_bits:
            raise HDLError(f"Memory address needs {address_bits} bits", index.token.line, index.token.column)
        previous = self.memory_addresses.get(name)
        if previous is not None and previous != index.value:
            raise HDLError("RAM has one address port: read and write must use the same address signal",
                           index.token.line, index.token.column)
        if previous is None:
            self.memory_addresses[name] = index.value
            source = self.expression(index, address_bits)
            target = _pin_vector(self._memory_component(name), "A", address_bits)
            _connect_vector(self.circuit, source, target)

    @staticmethod
    def _has_memory_target(statement):
        if isinstance(statement, ProcAssign):
            return isinstance(statement.target, tuple) and statement.target[0] != "bit"
        if isinstance(statement, ProcBlock): return any(_Builder._has_memory_target(s) for s in statement.statements)
        if isinstance(statement, ProcIf):
            return _Builder._has_memory_target(statement.yes) or bool(statement.no and _Builder._has_memory_target(statement.no))
        if isinstance(statement, ProcCase):
            return any(_Builder._has_memory_target(body) for _, body in statement.arms) or bool(statement.default and _Builder._has_memory_target(statement.default))
        return False

    def _compile_memory_writer(self, procedure):
        if procedure.reset and self._has_memory_target(procedure.body):
            raise HDLError("Asynchronous reset of an HDL memory array is unsupported",
                           procedure.token.line, procedure.token.column)
        body = procedure.body
        while isinstance(body, ProcBlock) and len(body.statements) == 1:
            body = body.statements[0]
        enable = None
        if isinstance(body, ProcIf) and body.no is None:
            enable = body.condition
            body = body.yes
            while isinstance(body, ProcBlock) and len(body.statements) == 1:
                body = body.statements[0]
        if (not isinstance(body, ProcAssign) or not isinstance(body.target, tuple) or
                body.target[0] == "bit"):
            if self._has_memory_target(procedure.body):
                raise HDLError("Memory write supports one optional if-enable and one assignment",
                               procedure.token.line, procedure.token.column)
            return False
        if procedure.kind != "clocked" or not body.nonblocking:
            raise HDLError("Memory writes need nonblocking assignment on one clock edge",
                           body.token.line, body.token.column)
        name, address = body.target
        if name in self.memory_writers:
            raise HDLError(f"Multiple writers for memory {name}", body.token.line, body.token.column)
        self.memory_writers.add(name)
        component = self._memory_component(name)
        self._memory_address(name, address)
        width = self.module.memories[name][0]
        data = self.expression(body.expr, width)
        if len(data) != width:
            raise HDLError(f"Memory write data needs {width} bits", body.token.line, body.token.column)
        _connect_vector(self.circuit, data, _pin_vector(component, "D", width))
        if enable is None:
            source = self.add("CONST", value=1)
            self.circuit.connect(source.id, "Q", component.id, "WE")
        else:
            selected = self.expression(enable)
            if len(selected) != 1:
                raise HDLError("Memory write enable must be one bit", enable.token.line, enable.token.column)
            self.circuit.connect(selected[0][0], selected[0][1], component.id, "WE")
        clock = self.resolve(procedure.clock, procedure.token)
        if len(clock) != 1:
            raise HDLError("Memory clock must be one bit", procedure.token.line, procedure.token.column)
        self.circuit.connect(clock[0][0], clock[0][1], component.id, "CLK")
        component.params["edge"] = "rising" if procedure.edge == "posedge" else "falling"
        return True

    def _async_reset_values(self, procedure):
        body = procedure.body
        while isinstance(body, ProcBlock) and len(body.statements) == 1:
            body = body.statements[0]
        if not isinstance(body, ProcIf) or body.no is None:
            raise HDLError("Asynchronous reset needs if(reset) ... else ...",
                           procedure.token.line, procedure.token.column)
        condition = body.condition
        active_high = procedure.reset_edge == "posedge"
        matches = (condition.kind == "name" and condition.value == procedure.reset if active_high else
                   condition.kind == "unary" and condition.value in ("!", "~") and
                   condition.left.kind == "name" and condition.left.value == procedure.reset)
        if not matches:
            raise HDLError("Reset condition must match the sensitivity edge",
                           condition.token.line, condition.token.column)
        reset_values = _procedural_values(body.yes, {}, True)
        data_values = _procedural_values(body.no, {}, True)
        if not reset_values or set(reset_values) != set(data_values):
            raise HDLError("Reset and data branches must assign the same complete targets",
                           body.token.line, body.token.column)
        concrete = {}
        for name, expr in reset_values.items():
            if not isinstance(name, str) or expr.kind != "literal" or name not in self.module.signals:
                raise HDLError("Reset branch needs full-vector literal assignments",
                               body.token.line, body.token.column)
            width = self.module.signals[name][1]
            literal_width, bits = _literal(expr, width)
            if literal_width != width or None in bits:
                raise HDLError("Reset value must be a known literal of the target width",
                               expr.token.line, expr.token.column)
            concrete[name] = sum(bit << bit_index for bit_index, bit in enumerate(bits))
        return data_values, concrete

    def add(self, kind, width=1, **params):
        c = self.circuit.add(kind, (self.next_x % 6) * 190, (self.next_x // 6) * 165,
                             {"width": width, **params})
        self.next_x += 1
        return c

    def terminal(self, direction, name, width):
        if self.clock_generators and direction == "input" and width == 1 and name in self.clock_names:
            component = self.add("Clock Generator", period=2, running=True, label=name,
                                 _hdl_clock_input=True)
            return [(component.id, "Q")]
        # Legacy block interfaces are terminal based and INPUT/OUTPUT cap at 8 bits.
        # Wide nested ports use scalar terminals with indexed labels.
        if self.nested and width > 8:
            parts = []
            for bit in range(width):
                c = self.add("INPUT" if direction == "input" else "OUTPUT", label=f"{name}{bit}")
                parts.append((c.id, "Q" if direction == "input" else "A"))
            if direction == "output": self.terminal_targets[name] = parts
            return parts
        kind = ("INPUT" if direction == "input" else "OUTPUT") if width <= 8 else ("Bus Input" if direction == "input" else "Bus Output")
        c = self.add(kind, width, label=name)
        if direction == "input" and name in self.reset_defaults:
            c.params["value"] = self.reset_defaults[name]
        parts = _pin_vector(c, "Q" if direction == "input" else ("A" if kind == "OUTPUT" else "D"), width)
        if direction == "output": self.terminal_targets[name] = parts
        return parts

    def resolve(self, name, token):
        if name not in self.module.signals:
            raise HDLError(f"Unknown signal {name}", token.line, token.column)
        if name in self.sources: return self.sources[name]
        if name in self.resolving:
            raise HDLError(f"Combinational assignment cycle at {name}", token.line, token.column)
        if name not in self.drivers:
            raise HDLError(f"Signal {name} has no driver", token.line, token.column)
        self.resolving.add(name)
        kind, item = self.drivers[name]
        result = self.expression(item, self.module.signals[name][1]) if kind == "assign" else item
        self.resolving.remove(name)
        if len(result) != self.module.signals[name][1]:
            raise HDLError(f"Width mismatch for {name}: expected {self.module.signals[name][1]}, got {len(result)}", token.line, token.column)
        self.sources[name] = result
        return result

    def expression(self, expr, expected=None):
        if expr.kind == "name": return self.resolve(expr.value, expr.token)
        if expr.kind == "concat":
            # Verilog lists most-significant part first; circuit pins are LSB first.
            parts = [self.expression(part) for part in expr.value]
            result = [pin for part in reversed(parts) for pin in part]
            if expected is not None and len(result) != expected:
                raise HDLError(f"Concatenation width mismatch: expected {expected}, got {len(result)}",
                               expr.token.line, expr.token.column)
            return result
        if expr.kind == "case_equal":
            if expr.right.kind != "literal":
                raise HDLError("Case equality supports a known literal on the right",
                               expr.token.line, expr.token.column)
            if expr.left.kind == "reduction_or":
                source = self.expression(expr.left.left)
                width, bits = _literal(expr.right, 1)
                if width != 1 or bits != [1]:
                    raise HDLError("Reduction OR case equality supports only 1'b1",
                                   expr.token.line, expr.token.column)
                gate = self.add("HDL Truth", len(source))
            else:
                source = self.expression(expr.left)
                width, bits = _literal(expr.right, len(source))
                if width != len(source) or None in bits:
                    raise HDLError("Case equality literal must be known and match the signal width",
                                   expr.token.line, expr.token.column)
                gate = self.add("HDL Case Match", len(source),
                                match=sum(bit << index for index, bit in enumerate(bits)))
            _connect_vector(self.circuit, source, _pin_vector(gate, "A", len(source)))
            return [(gate.id, "Q")]
        if expr.kind == "reduction_or":
            raise HDLError("Standalone reduction OR is unsupported; use a case-equality test",
                           expr.token.line, expr.token.column)
        if expr.kind == "replace_bit":
            base = self.expression(expr.left, expected)
            replacement = self.expression(expr.right, 1)
            width, index = len(base), expr.value
            if width not in BUS_WIDTHS or not 0 <= index < width or len(replacement) != 1:
                raise HDLError("Partial assignment needs an in-range vector bit and one-bit value",
                               expr.token.line, expr.token.column)
            merger = self.add("Bus Merger", width)
            for bit, (cid, pin) in enumerate(base):
                source_id, source_pin = replacement[0] if bit == index else (cid, pin)
                self.circuit.connect(source_id, source_pin, merger.id, f"D{bit}")
            return _pin_vector(merger, "Q", width)
        if expr.kind == "memory_read":
            self._memory_address(expr.value, expr.left)
            width = self.module.memories[expr.value][0]
            return _pin_vector(self._memory_component(expr.value), "Q", width)
        if expr.kind in ("truth", "case_match"):
            source = self.expression(expr.left)
            width = len(source)
            if expr.kind == "case_match":
                label_width, bits = _literal(expr.value, width)
                if label_width != width or None in bits:
                    raise HDLError("Case label must be a known value matching selector width",
                                   expr.token.line, expr.token.column)
                gate = self.add("HDL Case Match", width,
                                match=sum(bit << i for i, bit in enumerate(bits)))
            else:
                gate = self.add("HDL Truth", width)
            _connect_vector(self.circuit, source, _pin_vector(gate, "A", width))
            return [(gate.id, "Q")]
        if expr.kind == "bit":
            name, index = expr.value; parts = self.resolve(name, expr.token)
            if index >= len(parts): raise HDLError(f"Bit {index} is outside {name}", expr.token.line, expr.token.column)
            return [parts[index]]
        if expr.kind == "literal":
            width, bits = _literal(expr, expected)
            if width > 8:
                result = []
                for start in range(0, width, 8):
                    chunk = bits[start:start + 8]
                    c = self.add("CONST", len(chunk),
                                 value=None if None in chunk else sum(bit << i for i, bit in enumerate(chunk)))
                    if None in chunk: c.params["_bit_values"] = chunk
                    result.extend(_pin_vector(c, "Q", len(chunk)))
                return result
            c = self.add("CONST", width, value=None if None in bits else sum((bit << i) for i, bit in enumerate(bits) if bit is not None))
            if None in bits: c.params["_bit_values"] = bits
            return _pin_vector(c, "Q", width)
        if expr.kind == "unary":
            src = self.expression(expr.left, expected)
            if expr.value == "!" and len(src) != 1:
                raise HDLError("Logical ! accepts one-bit operands only", expr.token.line, expr.token.column)
            gate = self.add("NOT", len(src))
            _connect_vector(self.circuit, src, _pin_vector(gate, "A", len(src)))
            return _pin_vector(gate, "Q", len(src))
        if expr.kind == "binary":
            left = self.expression(expr.left, expected)
            right = self.expression(expr.right, len(left) if expr.right.kind == "literal" else expected)
            if expr.left.kind == "literal" and len(left) != len(right):
                left = self.expression(expr.left, len(right))
            if len(left) != len(right):
                raise HDLError(f"Operand width mismatch: {len(left)} versus {len(right)}", expr.token.line, expr.token.column)
            width = len(left)
            if expr.value in ("&&", "||") and width != 1:
                raise HDLError("Logical operators accept one-bit operands only", expr.token.line, expr.token.column)
            kind = {"&": "AND", "&&": "AND", "|": "OR", "||": "OR", "^": "XOR",
                    "+": "Adder", "-": "Subtractor", "*": "Multiplier", "/": "Divider"}[expr.value]
            gate = self.add(kind, width)
            _connect_vector(self.circuit, left, _pin_vector(gate, "A", width))
            _connect_vector(self.circuit, right, _pin_vector(gate, "B", width))
            if kind == "Adder":
                zero = self.add("CONST", value=0)
                self.circuit.connect(zero.id, "Q", gate.id, "CIN")
            return _pin_vector(gate, "Q", width)
        if expr.kind == "ternary":
            select = self.expression(expr.left)
            yes = self.expression(expr.value[0], expected)
            no = self.expression(expr.value[1], len(yes))
            if len(select) != 1 or len(yes) != len(no):
                raise HDLError("Multiplexer needs one-bit select and equal-width branches", expr.token.line, expr.token.column)
            width = len(yes); mux = self.add("Multiplexer", width)
            _connect_vector(self.circuit, no, _pin_vector(mux, "A", width))
            _connect_vector(self.circuit, yes, _pin_vector(mux, "B", width))
            self.circuit.connect(select[0][0], select[0][1], mux.id, "SEL")
            return _pin_vector(mux, "Q", width)
        raise HDLError("Unsupported expression", expr.token.line, expr.token.column)

    def build(self):
        m = self.module
        for name in m.header:
            direction, width = m.signals[name]
            pins_ = self.terminal(direction, name, width)
            if direction == "input": self.sources[name] = pins_
            else: self.drivers.setdefault(name, ("terminal", None))
        for name, expr, token in m.assignments:
            if name not in m.signals or m.signals[name][0] == "input":
                raise HDLError(f"Cannot assign {name}", token.line, token.column)
            if name in self.drivers and self.drivers[name][0] != "terminal":
                raise HDLError(f"Multiple drivers on {name}", token.line, token.column)
            self.drivers[name] = ("assign", expr)
        for procedure in m.procedures:
            if procedure.kind == "clocked":
                if procedure.clock not in m.signals or m.signals[procedure.clock][1] != 1:
                    raise HDLError("Clock must be a declared one-bit signal",
                                   procedure.token.line, procedure.token.column)
                if procedure.reset and (procedure.reset not in m.signals or
                                        m.signals[procedure.reset][1] != 1):
                    raise HDLError("Asynchronous reset must be a declared one-bit signal",
                                   procedure.token.line, procedure.token.column)
            if self._compile_memory_writer(procedure): continue
            values, reset_values = (self._async_reset_values(procedure) if procedure.reset else
                                    (_procedural_values(procedure.body, {}, procedure.kind == "clocked"), {}))
            if not values:
                raise HDLError("Procedural block assigns no signals",
                               procedure.token.line, procedure.token.column)
            for name, expr in values.items():
                if name not in m.signals or m.signals[name][0] == "input":
                    raise HDLError(f"Cannot procedurally assign {name}",
                                   procedure.token.line, procedure.token.column)
                if name in self.drivers and self.drivers[name][0] != "terminal":
                    raise HDLError(f"Multiple drivers on {name}",
                                   procedure.token.line, procedure.token.column)
                width = m.signals[name][1]
                if procedure.kind == "comb":
                    self.drivers[name] = ("assign", expr)
                else:
                    state = self.add("D Flip-Flop" if width == 1 else "Register", width,
                                     edge="rising" if procedure.edge == "posedge" else "falling",
                                     initial=None,
                                     **({"async_reset": True,
                                         "reset_active": 1 if procedure.reset_edge == "posedge" else 0,
                                         "reset_value": reset_values[name]} if procedure.reset else {}))
                    self.drivers[name] = ("state", _pin_vector(state, "Q", width))
                    self.sequential_inputs.append((state, expr, procedure.clock,
                                                   procedure.token, procedure.reset))
        for type_name, instance_name, connections, token in m.instances:
            if sum(name == instance_name for _, name, _, _ in m.instances) > 1:
                raise HDLError(f"Duplicate instance {instance_name}", token.line, token.column)
            if type_name not in self.definitions:
                raise HDLError(f"Unknown or cyclic module {type_name}", token.line, token.column)
            target = self.modules[type_name]
            if set(connections) != set(target.header):
                raise HDLError(f"Instance {instance_name}: connect every port of {type_name}", token.line, token.column)
            c = self.circuit.add("BLOCK:" + type_name, self.next_x * 170, 180)
            self.next_x += 1
            for port in target.header:
                direction, width = target.signals[port]
                expr = connections[port]
                if direction == "input":
                    self.instance_inputs.append((c, port, width, expr))
                else:
                    if expr.kind != "name" or expr.value not in m.signals:
                        raise HDLError("Instance outputs need a declared signal name", expr.token.line, expr.token.column)
                    name = expr.value
                    if m.signals[name][0] == "input":
                        raise HDLError(f"Instance output cannot drive input {name}", expr.token.line, expr.token.column)
                    if m.signals[name][1] != width:
                        raise HDLError(f"Width mismatch on {name}", expr.token.line, expr.token.column)
                    if name in self.drivers and self.drivers[name][0] != "terminal":
                        raise HDLError(f"Multiple drivers on {name}", expr.token.line, expr.token.column)
                    self.drivers[name] = ("instance", [(c.id, port if width == 1 else f"{port}{i}") for i in range(width)])
        for name in m.header:
            if m.signals[name][0] == "output":
                targets = self.terminal_targets[name]
                if self.drivers.get(name) == ("terminal", None):
                    del self.drivers[name]
                _connect_vector(self.circuit, self.resolve(name, m.token), targets)
        for c, port, width, expr in self.instance_inputs:
            source = self.expression(expr, width)
            if len(source) != width:
                raise HDLError(f"Width mismatch on instance input {port}", expr.token.line, expr.token.column)
            target = [(c.id, port if width == 1 else f"{port}{i}") for i in range(width)]
            _connect_vector(self.circuit, source, target)
        for state, expr, clock, token, reset in self.sequential_inputs:
            width = state.params["width"]
            data = self.expression(expr, width)
            if len(data) != width:
                raise HDLError(f"Sequential data width mismatch: expected {width}, got {len(data)}",
                               token.line, token.column)
            if any(cid == state.id for cid, _ in data):
                first = self.add("NOT", width)
                second = self.add("NOT", width)
                _connect_vector(self.circuit, data, _pin_vector(first, "A", width))
                _connect_vector(self.circuit, _pin_vector(first, "Q", width), _pin_vector(second, "A", width))
                data = _pin_vector(second, "Q", width)
            _connect_vector(self.circuit, data, _pin_vector(state, "D", width))
            source = self.resolve(clock, token)
            if len(source) != 1:
                raise HDLError("Clock must be one bit", token.line, token.column)
            self.circuit.connect(source[0][0], source[0][1], state.id, "CLK")
            if reset:
                reset_source = self.resolve(reset, token)
                if len(reset_source) != 1:
                    raise HDLError("Asynchronous reset must be one bit", token.line, token.column)
                self.circuit.connect(reset_source[0][0], reset_source[0][1], state.id, "ARST")
        problems = self.circuit.validate()
        if problems: raise HDLError("; ".join(problems), m.token.line, m.token.column)
        self.layout()
        return self.circuit

    def layout(self):
        """Place actual components in signal-flow columns; reject combinational cycles."""
        components = self.circuit.components
        incoming = {cid: set() for cid in components}
        downstream = {cid: set() for cid in components}
        for wire in self.circuit.wires.values():
            if components[wire.target].kind in SEQUENTIAL:
                continue  # state outputs break combinational dependency cycles
            incoming[wire.target].add(wire.source)
            downstream[wire.source].add(wire.target)
        ready = [cid for cid, parents in incoming.items() if not parents]
        depth = {cid: 0 for cid in ready}
        visited = 0
        while ready:
            cid = ready.pop(0); visited += 1
            for target in downstream[cid]:
                depth[target] = max(depth.get(target, 0), depth[cid] + 1)
                incoming[target].discard(cid)
                if not incoming[target]: ready.append(target)
        if visited != len(components):
            raise HDLError("Combinational feedback loop in imported module",
                           self.module.token.line, self.module.token.column)
        columns = {}
        for component in components.values():
            level = depth[component.id]
            columns.setdefault(level, []).append(component)
        for level, parts in columns.items():
            for index, component in enumerate(parts):
                component.x = level * 240
                component.y = (index - (len(parts) - 1) / 2) * 145

def import_verilog(source, top=None, *, clock_generators=False):
    if not isinstance(source, str) or len(source) > 1_000_000:
        raise HDLError("HDL source must be text of at most 1,000,000 characters")
    modules = parse(source)
    if top is None: top = list(modules)[-1]
    if top not in modules: raise HDLError(f"Unknown top module {top}")
    definitions, active = {}, set()

    def compile_module(name, nested):
        if name in active:
            module = modules[name]
            raise HDLError(f"Recursive module dependency: {name}", module.token.line, module.token.column)
        active.add(name)
        module = modules[name]
        for dependency, _, _, token in module.instances:
            if dependency not in modules:
                raise HDLError(f"Missing module {dependency}", token.line, token.column)
            if dependency not in definitions: compile_module(dependency, True)
        builder = _Builder(module, definitions, modules, nested,
                           clock_generators=clock_generators and not nested)
        circuit = builder.build()
        if not nested:
            source_id = uuid4().hex
            circuit.hdl_sources = {source_id: {"module": name, "source": source,
                                                "filename": ""}}
            for signal, parts in builder.sources.items():
                for cid, _ in parts:
                    component = circuit.components.get(cid)
                    if component is None: continue
                    component.params["_hdl_source_ref"] = source_id
                    signals = component.params.setdefault("_hdl_signals", [])
                    if signal not in signals: signals.append(signal)
            for component in circuit.components.values():
                if component.kind in ("INPUT", "OUTPUT", "Bus Input", "Bus Output", "Clock Generator"):
                    label = component.params.get("label")
                    if label in module.signals:
                        component.params["_hdl_source_ref"] = source_id
                        signals = component.params.setdefault("_hdl_signals", [])
                        if label not in signals: signals.append(label)
            for signal, expression, _ in module.assignments:
                for cid, _ in builder.sources.get(signal, []):
                    if cid in circuit.components:
                        circuit.components[cid].params.setdefault("_hdl_line", expression.token.line)
            for procedure in module.procedures:
                for component in circuit.components.values():
                    if (component.kind in ("D Flip-Flop", "Register") and
                            component.params.get("_hdl_source_ref") == source_id):
                        component.params.setdefault("_hdl_line", procedure.token.line)
        active.remove(name)
        if nested:
            definition = block_definition_from_circuit(circuit)
            definition["_hdl_bus_ports"] = {
                direction: {port: [f"{port}{index}" for index in range(width)]
                            for port, (kind, width) in module.signals.items()
                            if kind == direction and width in BUS_WIDTHS}
                for direction in ("input", "output")}
            definitions[name] = definition
        return circuit

    return compile_module(top, False)


def hdl_signal_components(circuit, source_id, signal):
    """Return real imported components producing a named HDL signal."""
    if not circuit.hdl_sources or source_id not in circuit.hdl_sources:
        return []
    matches = [component for component in circuit.components.values()
               if component.params.get("_hdl_source_ref") == source_id and
               signal in component.params.get("_hdl_signals", ())]
    return sorted(matches, key=lambda c: (c.kind in ("OUTPUT", "Bus Output"), c.id))


def validate_hdl(source, top=None):
    """Return diagnostics; an empty list means importable into the existing engine."""
    try: import_verilog(source, top)
    except (HDLError, ValueError) as error: return [str(error)]
    return []


def diagnose_hdl(source, top=None, filename="<editor>"):
    """Structured, actionable diagnostics; keeps the 2.4 string API intact."""
    try: import_verilog(source, top)
    except (HDLError, ValueError) as error:
        message = str(error).split(": ", 1)[-1] if isinstance(error, HDLError) else str(error)
        lowered = message.lower()
        if "latch inferred" in lowered:
            category, fix, severity = "latch-inference", "Assign the signal on every branch, or use a clocked block.", "warning"
        elif "width" in lowered or "bit" in lowered and "outside" in lowered:
            category, fix, severity = "width", "Use matching declared widths and explicit bit positions.", "error"
        elif "multiple driver" in lowered:
            category, fix, severity = "multiple-driver", "Keep one assign or procedural driver per signal.", "error"
        elif "sensitivity" in lowered or "clock" in lowered:
            category, fix, severity = "clock", "Use @(*) or one @(posedge/negedge clk) on a one-bit clock.", "error"
        else:
            category, fix, severity = "syntax-or-connectivity", "Check the supported HDL subset and the named signals and ports.", "error"
        return [Diagnostic(severity, category, filename,
                           error.line if isinstance(error, HDLError) else 1,
                           error.column if isinstance(error, HDLError) else 1,
                           message, fix)]
    return []


def prepare_import(circuit, destination):
    """Rename colliding HDL modules in every embedded snapshot before editor merge."""
    occupied = set(destination.blocks) | set(circuit.blocks)
    mapping = {}
    for name, definition in circuit.blocks.items():
        if name not in destination.blocks or destination.blocks[name] == definition: continue
        index = 2
        while f"{name}_hdl{index}" in occupied: index += 1
        replacement = f"{name}_hdl{index}"
        mapping[name] = replacement; occupied.add(replacement)
    if not mapping: return circuit

    def rewrite(snapshot):
        for component in snapshot.get("components", []):
            kind = component.get("kind", "")
            if kind.startswith("BLOCK:") and kind[6:] in mapping:
                component["kind"] = "BLOCK:" + mapping[kind[6:]]
        blocks = snapshot.get("blocks", {})
        for definition in blocks.values(): rewrite(definition["circuit"])
        snapshot["blocks"] = {mapping.get(name, name): definition for name, definition in blocks.items()}

    data = circuit.to_dict()
    rewrite(data)
    return Circuit.from_dict(data)


def run_vectors(source, vectors, top=None):
    """Run HDL vectors through an isolated real Circuit/Simulator, never the live editor."""
    return run_circuit_vectors(import_verilog(source, top), vectors)


def run_circuit_vectors(circuit, vectors):
    """Check labelled external terminals on a copy using the sole LogicSpace Simulator."""
    if (not isinstance(vectors, (list, tuple)) or len(vectors) > 5000
            or any(not isinstance(vector, dict) for vector in vectors)):
        raise ValueError("Test vectors must be a list of at most 5000 objects")
    circuit = Circuit.from_dict(deepcopy(circuit.to_dict()))
    sim = Simulator(circuit)
    if sim.errors: raise ValueError("Circuit simulation error: " + "; ".join(sim.errors))
    ins = {c.params.get("label"): c for c in circuit.components.values() if c.kind in ("INPUT", "Bus Input")}
    outs = {c.params.get("label"): c for c in circuit.components.values() if c.kind in ("OUTPUT", "Bus Output")}
    results = []
    for index, vector in enumerate(vectors):
        drive, expected = vector.get("inputs", {}), vector.get("expected", {})
        if not isinstance(drive, dict) or not isinstance(expected, dict):
            raise ValueError(f"Vector {index}: inputs and expected must be objects")
        if set(drive) != set(ins) or not set(expected) <= set(outs):
            raise ValueError(f"Vector {index}: specify all inputs and known output names")
        for name, value in drive.items():
            c = ins[name]; width = c.params.get("width", 1)
            if value is not None and (type(value) is not int or not 0 <= value < 1 << width):
                raise ValueError(f"Vector {index}: {name} does not fit {width} bits")
            c.params.pop("_bit_values", None)
            c.params["value"] = value
        sim.evaluate()
        if vector.get("step"): sim.step()
        actual = {}
        for name, c in outs.items():
            values = sim.inputs.get(c.id, {})
            width = c.params.get("width", 1)
            bits = [values.get("A" if width == 1 else ("A" if c.kind == "OUTPUT" else "D") + str(i)) for i in range(width)]
            actual[name] = None if None in bits else sum(bit << i for i, bit in enumerate(bits))
        for name, value in expected.items():
            width = outs[name].params.get("width", 1)
            if value is not None and (type(value) is not int or not 0 <= value < 1 << width):
                raise ValueError(f"Vector {index}: expected {name} does not fit {width} bits")
        results.append({"step": index, "actual": actual, "expected": expected,
                        "passed": all(actual[name] == value for name, value in expected.items())})
    return results


_EXPORTABLE = {"INPUT", "OUTPUT", "Bus Input", "Bus Output", "CONST",
               "Clock Generator",
               "AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR",
               "HDL Truth", "HDL Case Match",
               "Multiplexer", "Decoder", "Register", "D Flip-Flop",
               "Adder", "Subtractor", "Multiplier", "Divider", "Comparator",
               "Bus Splitter", "Bus Merger", "Bit Selector"}


def export_issues(circuit, active=()):
    """Enumerate every known obstacle before generating any HDL text."""
    issues = list(circuit.validate())
    labels = set()
    for c in circuit.components.values():
        if c.kind not in _EXPORTABLE and not c.kind.startswith("BLOCK:"):
            issues.append(f"{c.kind} {c.id}: no exact Verilog export model")
        if c.kind == "Clock Generator" and c.params.get("_hdl_clock_input") is not True:
            issues.append(f"Clock Generator {c.id}: only HDL-imported clock ports can export as inputs")
        if c.kind in ("INPUT", "OUTPUT", "Bus Input", "Bus Output") or c.kind == "Clock Generator" and c.params.get("_hdl_clock_input") is True:
            label = c.params.get("label", "")
            if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9$]*", label):
                issues.append(f"{c.kind} {c.id}: assign a valid HDL port label")
            elif label in labels:
                issues.append(f"Duplicate HDL port label {label}")
            labels.add(label)
        if c.kind.startswith("BLOCK:") and c.kind[6:] not in circuit.blocks:
            issues.append(f"Missing custom block {c.kind[6:]}")
        if c.kind.startswith("BLOCK:") and not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9$]*", c.kind[6:]):
            issues.append(f"Custom block {c.kind[6:]} needs an HDL identifier name")
    driven = {(w.target, target) for w in circuit.wires.values() for _, target in wire_bit_pairs(w)}
    for c in circuit.components.values():
        if c.kind not in _EXPORTABLE and not c.kind.startswith("BLOCK:"): continue
        if c.kind in ("INPUT", "Bus Input", "CONST", "Clock Generator"): continue
        for pin in pins(c, circuit.blocks)[0]:
            if (c.id, pin) not in driven:
                issues.append(f"{c.kind} {c.id}: input {pin} is disconnected")
    for name, definition in circuit.blocks.items():
        if not any(c.kind == "BLOCK:" + name for c in circuit.components.values()): continue
        if name in active:
            issues.append(f"Recursive custom block {name}")
            continue
        try:
            nested = Circuit.from_dict(definition["circuit"])
            issues.extend(f"Block {name}: {issue}" for issue in export_issues(nested, active + (name,)))
        except (ValueError, KeyError, TypeError) as error:
            issues.append(f"Block {name}: {error}")
    return issues


def _hdl_name(text):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9$]*", text):
        raise ValueError(f"Invalid HDL identifier {text!r}")
    return text


def _export_one(circuit, module_name):
    """Generate a structural module directly from Circuit pins and wire drivers."""
    ports, declarations, statements = [], [], []
    source = {}
    drivers = {(w.target, tp): (w.source, sp) for w in circuit.wires.values()
               for sp, tp in wire_bit_pairs(w)}
    components = list(circuit.components.values())
    for c in components:
        if c.kind in ("INPUT", "OUTPUT", "Bus Input", "Bus Output", "Clock Generator"):
            name = _hdl_name(c.params["label"]); width = c.params.get("width", 1)
            direction = "input" if c.kind in ("INPUT", "Bus Input", "Clock Generator") else "output"
            ports.append(name)
            declarations.append(f"  {direction} {'[' + str(width-1) + ':0] ' if width > 1 else ''}{name};")
            if direction == "input":
                for bit, pin in enumerate(pins(c, circuit.blocks)[1]):
                    source[c.id, pin] = name if width == 1 else f"{name}[{bit}]"
        elif c.kind == "CONST":
            width = c.params.get("width", 1)
            bits = c.params.get("_bit_values")
            if bits is None:
                value = c.params.get("value", 1)
                bits = [None if value is None else (value >> bit) & 1 for bit in range(width)]
            for bit, pin in enumerate(pins(c, circuit.blocks)[1]):
                source[c.id, pin] = f"1'b{'x' if bits[bit] is None else bits[bit]}"
        else:
            outputs = pins(c, circuit.blocks)[1]
            if c.kind.startswith("BLOCK:"):
                for pin in outputs:
                    name = f"n_{c.id}_{pin.replace('!', 'n')}"
                    declarations.append(f"  wire {name};"); source[c.id, pin] = name
            elif outputs:
                width = c.params.get("width", 1)
                if c.kind in ("Decoder", "Comparator", "Adder", "D Flip-Flop", "Bit Selector"):
                    # These can expose several independently named outputs.
                    group = [p for p in outputs if p == "Q" or re.fullmatch(r"Q\d+", p)]
                else: group = outputs
                if group and group == outputs and len(group) == width:
                    name = f"n_{c.id}_Q"
                    type_ = "reg" if c.kind in ("Register", "D Flip-Flop") else "wire"
                    initial = c.params.get("initial", 0)
                    suffix = (f" = {width}'d{initial};" if type_ == "reg" and initial is not None else ";")
                    declarations.append(f"  {type_} {'[' + str(width-1) + ':0] ' if width > 1 else ''}{name}" + suffix)
                    for bit, pin in enumerate(group):
                        source[c.id, pin] = name if width == 1 else f"{name}[{bit}]"
                else:
                    for pin in outputs:
                        name = f"n_{c.id}_{pin.replace('!', 'n')}"
                        type_ = "reg" if c.kind == "D Flip-Flop" and pin == "Q" else "wire"
                        initial = c.params.get("initial", 0)
                        suffix = (f" = 1'd{initial};" if type_ == "reg" and initial is not None else ";")
                        declarations.append(f"  {type_} {name}" + suffix)
                        source[c.id, pin] = name

    def pin(c, name):
        return source[drivers[c.id, name]]

    def vec(c, base, width, single=False):
        bits = [pin(c, base if single else (base if width == 1 else f"{base}{i}")) for i in range(width)]
        if width == 1: return bits[0]
        names = [re.fullmatch(r"(.+)\[(\d+)\]", bit) for bit in bits]
        if all(match and match.group(1) == names[0].group(1) and int(match.group(2)) == index
               for index, match in enumerate(names)):
            return names[0].group(1)
        return "{" + ", ".join(reversed(bits)) + "}"

    def out(c, name): return source[c.id, name]

    for c in components:
        k = c.kind; width = c.params.get("width", 1)
        if k in ("INPUT", "Bus Input", "CONST", "Clock Generator"): continue
        if k in ("OUTPUT", "Bus Output"):
            target = c.params["label"]
            operand = vec(c, "A" if k == "OUTPUT" else "D", width)
            statements.append(f"  assign {target} = {operand};")
        elif k.startswith("BLOCK:"):
            definition = circuit.blocks[k[6:]]
            connections = []
            for external in definition["inputs"]:
                connections.append(f".{external}({pin(c, external)})")
            for external in definition["outputs"]:
                connections.append(f".{external}({out(c, external)})")
            statements.append(f"  {_hdl_name(k[6:])} u_{c.id} (" + ", ".join(connections) + ");")
        elif k in ("AND", "OR", "XOR", "NAND", "NOR", "XNOR"):
            op = {"AND": "&", "OR": "|", "XOR": "^", "NAND": "&", "NOR": "|", "XNOR": "^"}[k]
            result = f"({vec(c, 'A', width)} {op} {vec(c, 'B', width)})"
            if k in ("NAND", "NOR", "XNOR"): result = "~" + result
            statements.append(f"  assign {vec_out(c, source, 'Q', width)} = {result};")
        elif k == "NOT":
            statements.append(f"  assign {vec_out(c, source, 'Q', width)} = ~{vec(c, 'A', width)};")
        elif k == "HDL Truth":
            statements.append(f"  assign {out(c, 'Q')} = (|{vec(c, 'A', width)}) === 1'b1;")
        elif k == "HDL Case Match":
            statements.append(f"  assign {out(c, 'Q')} = {vec(c, 'A', width)} === {width}'d{c.params['match']};")
        elif k == "Multiplexer":
            statements.append(f"  assign {vec_out(c, source, 'Q', width)} = {pin(c, 'SEL')} ? {vec(c, 'B', width)} : {vec(c, 'A', width)};")
        elif k == "Decoder":
            for index in range(4):
                statements.append(f"  assign {out(c, f'Q{index}')} = {{ {pin(c, 'B')}, {pin(c, 'A')} }} == 2'd{index};")
        elif k == "Comparator":
            left, right = vec(c, "A", width), vec(c, "B", width)
            for output, op in (("LT", "<"), ("EQ", "=="), ("GT", ">")):
                statements.append(f"  assign {out(c, output)} = {left} {op} {right};")
        elif k in ("Adder", "Subtractor", "Multiplier", "Divider"):
            left, right, result = vec(c, "A", width), vec(c, "B", width), vec_out(c, source, "Q", width)
            if k == "Adder":
                carry = pin(c, "CIN")
                result_bits = result[1:-1] if result.startswith("{") and result.endswith("}") else result
                statements.append(f"  assign {{ {out(c, 'COUT')}, {result_bits} }} = {{1'b0, {left}}} + {{1'b0, {right}}} + {carry};")
            elif k == "Divider":
                statements.append(f"  assign {result} = ({right} == 0) ? {width}'b{'x' * width} : {left} / {right};")
            else:
                statements.append(f"  assign {result} = {left} {'-' if k == 'Subtractor' else '*'} {right};")
        elif k in ("Register", "D Flip-Flop"):
            data = vec(c, "D", width if k == "Register" else 1)
            output = vec_out(c, source, "Q", width if k == "Register" else 1)
            edge = "posedge" if c.params.get("edge", "rising") == "rising" else "negedge"
            if c.params.get("async_reset"):
                reset_edge = "posedge" if c.params.get("reset_active", 1) == 1 else "negedge"
                reset_test = pin(c, "ARST") if reset_edge == "posedge" else f"!{pin(c, 'ARST')}"
                reset_value = c.params.get("reset_value", 0)
                statements.append(f"  always @({edge} {pin(c, 'CLK')} or {reset_edge} {pin(c, 'ARST')}) "
                                  f"if ({reset_test}) {output} <= {width}'d{reset_value}; "
                                  f"else {output} <= {data};")
            else:
                statements.append(f"  always @({edge} {pin(c, 'CLK')}) {output} <= {data};")
            if k == "D Flip-Flop": statements.append(f"  assign {out(c, '!Q')} = ~{output};")
        elif k in ("Bus Splitter", "Bus Merger", "Bit Selector"):
            if k == "Bus Splitter":
                for output in pins(c, circuit.blocks)[1]:
                    statements.append(f"  assign {out(c, output)} = {pin(c, 'D' + output[1:])};")
            elif k == "Bus Merger":
                for i in range(width): statements.append(f"  assign {out(c, f'Q{i}')} = {pin(c, f'D{i}')};")
            else: statements.append(f"  assign {out(c, 'Q')} = {pin(c, f'D{c.params.get('index', 0)}')};")
    return "module " + _hdl_name(module_name) + "(" + ", ".join(ports) + ");\n" + "\n".join(declarations + statements) + "\nendmodule\n"


def vec_out(component, mapping, base, width):
    if width == 1: return mapping[component.id, base]
    parts = [mapping[component.id, f"{base}{i}"] for i in range(width)]
    names = [re.match(r"(.+)\[\d+\]$", part) for part in parts]
    if all(match and match.group(1) == names[0].group(1) for match in names):
        return names[0].group(1)
    return "{" + ", ".join(reversed(parts)) + "}"


def export_verilog(circuit, module_name="logicspace_top"):
    issues = export_issues(circuit)
    if issues: raise ValueError("Cannot export Verilog:\n" + "\n".join(issues))
    emitted, active = [], set()
    def emit(current, name):
        if name in active: raise ValueError(f"Recursive custom block {name}")
        active.add(name)
        for block_name in current.blocks:
            if any(c.kind == "BLOCK:" + block_name for c in current.components.values()) and block_name not in emitted_names:
                definition = current.blocks[block_name]
                emit(Circuit.from_dict(definition["circuit"]), block_name)
        emitted.append(_export_one(current, name)); emitted_names.add(name)
        active.remove(name)
    emitted_names = set()
    emit(circuit, module_name)
    return "\n".join(emitted)
