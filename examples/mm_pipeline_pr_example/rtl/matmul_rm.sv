`timescale 1ns/1ps
// "MatMul" RM (functional surrogate for paper §5.1).
// Real matmul preloads a small matrix and streams a vector through; for
// sim-time evaluation we use an algebraically-equivalent 2-stage pipeline
// so the DPI bridge round-trip is exercised the same way.
module matmul_rm (
    input  wire        clk,
    input  wire [31:0] data_in,
    output reg  [31:0] result
);
    // y = (x * 3) + 5 — two pipeline stages
    reg [31:0] stage0;
    always @(posedge clk) begin
        stage0 <= data_in * 32'sd3;
        result <= stage0 + 32'sd5;
    end
endmodule
