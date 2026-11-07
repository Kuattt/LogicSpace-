module rom_module(input [1:0] addr, output [7:0] q);
  logic [7:0] words [0:3];
  initial begin
    words[0] = 8'h01;
    words[1] = 8'h02;
    words[2] = 8'h04;
    words[3] = 8'h08;
  end
  assign q = words[addr];
endmodule
