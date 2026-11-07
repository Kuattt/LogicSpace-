# LogicSpace 2.5 examples

Open a `.sv` file in **View → HDL / Verilog…**, select its top module and choose **Import to canvas**. Each imported component and wire is editable. In **Test vectors**, set `step: true` for clocked vectors. The first clock vector should be 0 for rising-edge examples.

| File | Behavior | Suggested check |
| --- | --- | --- |
| `d_flip_flop.sv` | Rising-edge D Flip-Flop | `clk=0,d=1` then `clk=1,d=1` gives `q=1` after Step |
| `register8.sv` | 8-bit register with synchronous reset | Drive `rst=1`, take a rising edge, then `q=0`; next rising edge with `rst=0,d=42` gives `q=42` |
| `counter8.sv` | 8-bit wrapping counter | Reset on a rising edge, then successive rising edges yield 1, 2, … modulo 256 |
| `shift_register.sv` | Four one-bit stages | Rising edges shift `d` through `q0`, `q1`, `q2`, `q3` |
| `simple_fsm.sv` | Two-state pulse controller | Reset on a rising edge; `start=1` on the next rising edge makes `done=1` for one cycle |
| `ram_module.sv` | Four-word RAM with HDL initialization | Read address 1 gives `0x34`; write `0x5A` with `we=1` on a rising edge and read the new value |
| `rom_module.sv` | Four-word initialized ROM | Addresses 0–3 read `1`, `2`, `4`, `8` |
| `ram_module.json` | Editable 16×8 RAM with synchronous read | Open as a circuit; set address 1, step a rising clock and the Bus Probe reads `0x2A`; write `0x5A` with `WRITE=1` on a rising edge |

`ram_module.json` is a native LogicSpace circuit with synchronous read. The HDL RAM subset uses asynchronous read, showing a different supported timing policy. Both use the same RAM component and BusWire implementation in the Simulator. None of these examples models physical FPGA timing.
