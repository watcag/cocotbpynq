`timescale 1ns/1ps
// Reconfigurable module: result = data_in + 0x1000
module compute_rm (
    input  wire        clk,
    input  wire [31:0] data_in,
    output reg  [31:0] result
);
    always @(posedge clk)
        result <= data_in + 32'h0000_1000;
endmodule
