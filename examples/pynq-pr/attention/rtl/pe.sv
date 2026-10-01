/* verilator lint_off WIDTHEXPAND */
`timescale 1ps / 1ps

module pe
#(
    parameter integer D_W     = 8,      // operand data width
    parameter integer D_W_ACC = 32      // accumulator data width
)
(
    input  wire                      clk,
    input  wire                      rst,
    input  wire                      init,
    input  wire signed [D_W-1:0]     in_a,
    input  wire signed [D_W-1:0]     in_b,
    input  wire signed [D_W_ACC-1:0] in_data,
    input  wire                      in_valid,
    output reg  signed [D_W-1:0]     out_a,
    output reg  signed [D_W-1:0]     out_b,
    output reg  signed [D_W_ACC-1:0] out_data,
    output reg                       out_valid
);

wire signed [2*D_W-1:0]   mult_op;
(* use_dsp = "yes" *) reg  signed [D_W_ACC-1:0] out_sum;
reg  signed [D_W_ACC-1:0] in_data_r;
reg                       in_valid_r;

assign mult_op = in_a * in_b;

always @(posedge clk) begin
    if (rst) begin
        out_a      <= {D_W{1'b0}};
        out_b      <= {D_W{1'b0}};
        out_sum    <= {D_W_ACC{1'b0}};
        in_data_r  <= {D_W_ACC{1'b0}};
        in_valid_r <= 1'b0;
        out_data   <= {D_W_ACC{1'b0}};
        out_valid  <= 1'b0;
    end else begin
        out_a <= in_a;
        out_b <= in_b;
        
        in_data_r  <= in_data;
        in_valid_r <= in_valid;
        
        if (init) begin
            out_sum   <= mult_op;
            out_data  <= out_sum;
            out_valid <= 1'b1;
        end else begin
            out_sum   <= out_sum + mult_op;
            out_data  <= in_data_r;
            out_valid <= in_valid_r;
        end
    end
end
 
endmodule
/* verilator lint_on WIDTHEXPAND */
