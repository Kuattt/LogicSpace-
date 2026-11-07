# 8-bit CPU Assembly examples

Each `.asm` file is paired with a complete wired LogicSpace `.json` project, a 256-byte `.bin` ROM image, and Intel HEX `.hex` machine code. The JSON project embeds the source and the ROM bytes, so open it directly in LogicSpace and choose **View → CPU / Assembly**. Press **Step instruction** or **Start / Resume**. All five programs finish with `HLT`.

| Program | What it does | Expected result |
| --- | --- | --- |
| `arithmetic` | Adds then subtracts | R0=10, R1=5 |
| `loop` | Counts to five with `CMP` and `JNZ` | R0=5 |
| `memory` | Writes and reads RAM address 0x20 | R0=42, RAM[0x20]=42 |
| `fibonacci` | Eight Fibonacci iterations | R0=21, R1=34, R3=0 |
| `stack` | Uses `PUSH`, `CALL`, `RET`, `POP` | R0=14, R2=7, SP=0xFF |

Run `python3 examples/build_cpu_programs.py` from the LogicSpace directory to regenerate the `.json`, `.hex`, and `.bin` files from the Assembly sources. The builder uses `assemble()` only to create ROM data; each project's CPU runs through LogicSpace components and wires.
