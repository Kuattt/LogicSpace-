// The select signal chooses one complete four-bit bus.
module mux4(input [3:0] a, input [3:0] b, input sel, output [3:0] y);
  assign y = sel ? b : a;
endmodule
