`timescale 1ns/1ps
// Stage 1 RM: result = data_in * 2
module stage1_rm (
    input  wire        clk,
    input  wire [31:0] data_in,
    output reg  [31:0] result
);
    always @(posedge clk)
        result <= data_in << 1;
endmodule
