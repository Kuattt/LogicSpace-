# LogicSpace 3.0 HDL examples

Open either `.sv` file in **View → HDL / Verilog…**, then choose **Validate** and **Import to canvas**. The imported parts are ordinary editable LogicSpace components.

- `async_reset_ff.sv`: `rst_n=0` clears `q` immediately, without a clock step. With `rst_n=1`, a rising `clk` captures `d`.
- `partial_register.sv`: each rising `clk` updates only bits 0 and 2. Bits 1 and 3 remain unknown until explicitly driven through another design.

These are logical circuit examples. No physical propagation, setup or hold time is modeled.
