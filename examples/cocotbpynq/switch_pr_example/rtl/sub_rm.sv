`timescale 1ns/1ps
// RM variant: result = data_in - 3
module sub_rm (
    input  wire        clk,
    input  wire [31:0] data_in,
    output reg  [31:0] result
);
    always @(posedge clk)
        result <= data_in - 32'sd3;
endmodule
