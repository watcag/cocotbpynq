`timescale 1ns/1ps
// RP0 variant: result = data_in + 1
module rp0_rm (
    input  wire        clk,
    input  wire [31:0] data_in,
    output reg  [31:0] result
);
    always @(posedge clk)
        result <= data_in + 32'd1;
endmodule
