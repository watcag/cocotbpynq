`timescale 1ns/1ps
// Reconfigurable module: result = ~data_in
module compute_rm (
    input  wire        clk,
    input  wire [31:0] data_in,
    output reg  [31:0] result
);
    always @(posedge clk)
        result <= ~data_in;
endmodule
