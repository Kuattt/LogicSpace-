module counter8(input clk, input rst, output logic [7:0] q);
  always_ff @(posedge clk) begin
    if (rst) q <= 8'd0;
    else q <= q + 8'd1;
  end
endmodule
