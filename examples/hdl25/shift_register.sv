module shift_register(input clk, input d, output logic q0, output logic q1,
                      output logic q2, output logic q3);
  always_ff @(posedge clk) begin
    q0 <= d;
    q1 <= q0;
    q2 <= q1;
    q3 <= q2;
  end
endmodule
