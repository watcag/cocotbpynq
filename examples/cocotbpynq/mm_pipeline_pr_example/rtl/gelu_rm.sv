`timescale 1ns/1ps
// "GELU" variant of the nonlin_rm slot (partition rp1).
// GELU(x) ≈ x*2 when x>=0, else 0 — simplified surrogate for paper §5.1.
module nonlin_rm (
    input  wire        clk,
    input  wire [31:0] data_in,
    output reg  [31:0] result
);
    reg signed [31:0] stage0;
    always @(posedge clk) begin
        stage0 <= $signed(data_in);
        result <= (stage0 >= 0) ? (stage0 <<< 1) : 32'sd0;
    end
endmodule
