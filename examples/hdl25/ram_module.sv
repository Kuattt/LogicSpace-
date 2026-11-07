module ram_module(input clk, input we, input [1:0] addr,
                  input [7:0] d, output [7:0] q);
  logic [7:0] mem [0:3];
  initial begin
    mem[0] = 8'h12;
    mem[1] = 8'h34;
  end
  always_ff @(posedge clk) begin
    if (we) mem[addr] <= d;
  end
  assign q = mem[addr];
endmodule
