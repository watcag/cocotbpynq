`timescale 1ns/1ps
// RP1 variant: result = data_in * 3
module rp1_rm (
    input  wire        clk,
    input  wire [31:0] data_in,
    output reg  [31:0] result
);
    always @(posedge clk)
        result <= data_in + (data_in << 1);
endmodule
