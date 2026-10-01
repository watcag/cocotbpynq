`timescale 1ns/1ps
// "Softmax" variant of the nonlin_rm slot (partition rp1).
// y = (x * 7) & 0xFF — simplified surrogate for paper §5.1.
module nonlin_rm (
    input  wire        clk,
    input  wire [31:0] data_in,
    output reg  [31:0] result
);
    reg [31:0] stage0;
    always @(posedge clk) begin
        stage0 <= data_in * 32'sd7;
        result <= stage0 & 32'h000000FF;
    end
endmodule
