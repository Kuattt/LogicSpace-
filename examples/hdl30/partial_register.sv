// Only Q[0] and Q[2] are written. Unwritten bits retain their prior values,
// including X before the first write.
module partial_register(input clk, input a, input b, output logic [3:0] q);
  always_ff @(posedge clk) begin
    q[0] <= a;
    q[2] <= b;
  end
endmodule
