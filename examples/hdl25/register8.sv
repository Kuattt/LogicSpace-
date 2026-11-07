module register8(input clk, input rst, input [7:0] d, output logic [7:0] q);
  always_ff @(posedge clk) begin
    if (rst) q <= 8'd0;
    else q <= d;
  end
endmodule
