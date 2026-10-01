`timescale 1ps / 1ps

module sreg
#(
    parameter integer D_W = 32,
    parameter integer DEPTH = 8
)
(
    input wire clk,
    input wire rst,
    input wire shift_en,
    input wire signed [D_W-1:0] data_in,
    output wire signed [D_W-1:0] data_out
);

reg [DEPTH-1:0][D_W-1:0] mem;

always @(posedge clk) begin
    if (shift_en) begin
        mem <= {mem[DEPTH-2:0],data_in};
    end
end

assign data_out = mem[DEPTH-1];

endmodule
