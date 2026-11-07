// Named instance connections become a reusable LogicSpace custom block.
module xor_bit(input a, input b, output y);
  assign y = a ^ b;
endmodule

module nested_xor(input a, input b, output y);
  xor_bit u0(.a(a), .b(b), .y(y));
endmodule
