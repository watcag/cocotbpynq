`timescale 1ns/1ps
// RM variant: result = data_in * 10
module mult_rm (
    input  wire        clk,
    input  wire [31:0] data_in,
    output reg  [31:0] result
);
    always @(posedge clk)
        result <= data_in * 32'sd10;
endmodule
