/* verilator lint_off WIDTHEXPAND */
`timescale 1ps / 1ps

module mem_write_D
#(
    parameter integer D_W    = 32,
    parameter integer N1     = 4,
    parameter integer MATRIXSIZE_W = 16,
    parameter integer ADDR_W = 12
)
(
    input  wire                           clk,
    input  wire                           rst,
    input  wire        [MATRIXSIZE_W-1:0] M1xM3dN1,
    input  wire        [N1-1:0]           in_valid,
    input  wire signed [D_W-1:0]          in_data [N1-1:0],
    output reg         [ADDR_W-1:0]       wr_addr_bram [N1-1:0],
    output wire signed [D_W-1:0]          wr_data_bram [N1-1:0],
    output wire        [N1-1:0]           wr_en_bram
);

assign wr_data_bram = in_data;
assign wr_en_bram   = (rst == 1) ? 0 : in_valid;

genvar x;
for (x = 0; x < N1; x = x + 1) begin
    always @(posedge clk) begin
        if (rst) begin
            wr_addr_bram[x] <= 0;
        end else if (in_valid[x] == 1'b1) begin
            wr_addr_bram[x] <= wr_addr_bram[x] < (M1xM3dN1 - 1) ? (wr_addr_bram[x] + 1) : 0;
        end
    end
end

endmodule
/* verilator lint_on WIDTHEXPAND */
