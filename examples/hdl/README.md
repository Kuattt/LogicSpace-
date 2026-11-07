# HDL examples

Open each `.v` file in **View → HDL / Verilog**, choose the top module and click **Import to canvas**. The imported circuit contains real editable components and wires.

Useful test vectors (paste as a JSON list in the Test vectors tab):

```json
[
  {"inputs": {"a": 10, "b": 12}, "expected": {"y": 8}},
  {"inputs": {"a": 15, "b": 3}, "expected": {"y": 3}}
]
```

The vectors above apply to `and4.v`. For `mux4.v`, include `sel` and set `y` to `a` when `sel=0` or `b` when `sel=1`.
