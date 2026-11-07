module simple_fsm(input clk, input reset, input start, output logic done);
  logic state;
  logic next_state;
  always_comb begin
    case (state)
      1'b0: next_state = start;
      1'b1: next_state = 1'b0;
      default: next_state = 1'b0;
    endcase
  end
  always_ff @(posedge clk) begin
    if (reset) state <= 1'b0;
    else state <= next_state;
  end
  assign done = state;
endmodule
