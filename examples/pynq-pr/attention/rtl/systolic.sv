/* verilator lint_off WIDTHEXPAND */
`timescale 1ps / 1ps

module systolic
#(
    parameter integer D_W     = 8,      // operand data width
    parameter integer D_W_ACC = 32,     // accumulator data width
    parameter integer N1      = 8,
    parameter integer N2      = 4
)
(
    input  wire                      clk,
    input  wire                      rst,
    input  wire        [N2-1:0]      init [N1-1:0],
    input  wire signed [D_W-1:0]     A    [N1-1:0],
    input  wire signed [D_W-1:0]     B    [N2-1:0],
    output wire signed [D_W_ACC-1:0] D    [N1-1:0],
    output wire        [N1-1:0]      valid_D
);

wire signed [D_W-1:0]     a_wire     [N1-1:0][N2:0];
wire signed [D_W-1:0]     b_wire     [N1:0][N2-1:0];
wire signed [D_W_ACC-1:0] data_wire  [N1-1:0][N2:0];
wire        [N2:0]        valid_wire [N1-1:0];

reg  signed [D_W-1:0]     A_reg      [N1-1:0];
reg  signed [D_W-1:0]     B_reg      [N2-1:0];
reg         [N2-1:0]      init_reg   [N1-1:0];

integer x;
always @(posedge clk) begin
    if (rst) begin
        for (x = 0; x < N1; x = x + 1) begin
            A_reg[x]    <= 0;
            init_reg[x] <= 0;
        end
        for (x = 0; x < N2; x = x + 1) begin
            B_reg[x] <= 0;
        end
    end else begin
        for (x = 0; x < N1; x = x + 1) begin
            A_reg[x]    <= A[x];
            init_reg[x] <= init[x];
        end
        for (x = 0; x < N2; x = x + 1) begin
            B_reg[x] <= B[x];
        end
    end
end

genvar i, j;
generate
    `ifdef DSP_HPACK
    for (i = 0; i < N1; i = i + 1) begin
        assign data_wire[i][0]  = {D_W{1'b0}};
        assign valid_wire[i][0] = 1'b0;

        for (j = 0; j < N2; j = j + 2) begin
            pe_hp #(
                .D_W     (D_W),
                .D_W_ACC (D_W_ACC)
            )
            pe_inst (
                .clk        (clk),
                .rst        (rst),
                .init       (init_reg[i][j]),
                .in_a       (j == 0 ? A_reg[i] : a_wire[i][j]),
                .in_b1      (i == 0 ? B_reg[j] : b_wire[i][j]),
                .in_b2      (i == 0 ? B_reg[j+1] : b_wire[i][j+1]),
                .in_data    (data_wire[i][j]),
                .in_valid   (valid_wire[i][j]),
                .out_a      (a_wire[i][j+2]),
                .out_b1     (b_wire[i+1][j]),
                .out_b2     (b_wire[i+1][j+1]),
                .out_data   (data_wire[i][j+2]),
                .out_valid  (valid_wire[i][j+2])
            );
        end

        assign D[i]       = data_wire[i][N2];
        assign valid_D[i] = valid_wire[i][N2];
    end
    `elsif DSP_VPACK
    for (i = 0; i < N1; i = i + 2) begin
        assign data_wire[i][0]    = {D_W{1'b0}};
        assign valid_wire[i][0]   = 1'b0;
        assign data_wire[i+1][0]  = {D_W{1'b0}};
        assign valid_wire[i+1][0] = 1'b0;

        for (j = 0; j < N2; j = j + 1) begin
            pe_vp #(
                .D_W     (D_W),
                .D_W_ACC (D_W_ACC)
            )
            pe_inst (
                .clk        (clk),
                .rst        (rst),
                .init       (init_reg[i][j]),
                .in_a1      (j == 0 ? A_reg[i] : a_wire[i][j]),
                .in_a2      (j == 0 ? A_reg[i+1] : a_wire[i+1][j]),
                .in_b       (i == 0 ? B_reg[j] : b_wire[i][j]),
                .in_data1   (data_wire[i][j]),
                .in_valid1  (valid_wire[i][j]),
                .in_data2   (data_wire[i+1][j]),
                .in_valid2  (valid_wire[i+1][j]),
                .out_a1     (a_wire[i][j+1]),
                .out_a2     (a_wire[i+1][j+1]),
                .out_b      (b_wire[i+2][j]),
                .out_data1  (data_wire[i][j+1]),
                .out_valid1 (valid_wire[i][j+1]),
                .out_data2  (data_wire[i+1][j+1]),
                .out_valid2 (valid_wire[i+1][j+1])
            );
        end

        assign D[i]         = data_wire[i][N2];
        assign valid_D[i]   = valid_wire[i][N2];
        assign D[i+1]       = data_wire[i+1][N2];
        assign valid_D[i+1] = valid_wire[i+1][N2];
    end
    `else
    for (i = 0; i < N1; i = i + 1) begin
        assign data_wire[i][0]  = {D_W{1'b0}};
        assign valid_wire[i][0] = 1'b0;

        for (j = 0; j < N2; j = j + 1) begin
            pe #(
                .D_W     (D_W),
                .D_W_ACC (D_W_ACC)
            )
            pe_inst (
                .clk       (clk),
                .rst       (rst),
                .init      (init_reg[i][j]),
                .in_a      (j == 0 ? A_reg[i] : a_wire[i][j]),
                .in_b      (i == 0 ? B_reg[j] : b_wire[i][j]),
                .in_data   (data_wire[i][j]),
                .in_valid  (valid_wire[i][j]),
                .out_a     (a_wire[i][j+1]),
                .out_b     (b_wire[i+1][j]),
                .out_data  (data_wire[i][j+1]),
                .out_valid (valid_wire[i][j+1])
            );
        end

        assign D[i]       = data_wire[i][N2];
        assign valid_D[i] = valid_wire[i][N2];
    end
    `endif
endgenerate

endmodule
/* verilator lint_on WIDTHEXPAND */
