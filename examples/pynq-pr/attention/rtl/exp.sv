`timescale 1ps / 1ps

module exp
#(
    parameter integer D_W     = 32,
    parameter integer FP_BITS = 30
)
(
    input  wire                  clk,
    input  wire                  rst,
    input  wire                  enable,
    input  wire                  in_valid,
    input  wire signed [D_W-1:0] qin,
    input  wire signed [16-1:0]  qb,
    input  wire signed [24-1:0]  qc,
    input  wire signed [12-1:0]  qln2,
    input  wire signed [24-1:0]  qln2_inv,
    output wire                  out_valid,
    output wire signed [D_W-1:0] qout
);
/* verilator lint_off WIDTHEXPAND */

reg signed [D_W-1:0] qin_r0, qin_r1p, qin_r1, qin_r2p, qin_r2;
reg signed [D_W-1:0] qout_r;

reg signed [38-1:0] qp_r2p, qp_r2, qp_r3, qp_r4;
reg signed [38-1:0] ql_r4;
reg signed [2*D_W-1:0] ql_r5p, ql_r5, ql_r6;

reg signed [16-1:0] qb_r0;
reg signed [24-1:0] qc_r0;
reg signed [12-1:0] qln2_r0;
reg signed [24-1:0] qln2_inv_r0;

reg in_v_r0, in_v_r1p, in_v_r1, in_v_r2p, in_v_r2, in_v_r3, in_v_r4, in_v_r5p, in_v_r5, in_v_r6;
reg done;

wire signed [D_W+24-1:0] fp_mul;
reg signed [D_W+24-FP_BITS-1:0] z_r1p, z_r1;
reg signed [$clog2(2*D_W):0] z_r2p, z_r2, z_r3, z_r4, z_r5p, z_r5, z_r6;

assign qout      = qout_r;
assign out_valid = done;
assign fp_mul    = qin_r0 * qln2_inv_r0;

always @(posedge clk) begin
    if (rst) begin
        in_v_r0 <= 0;
        in_v_r1 <= 0;
        in_v_r2 <= 0;
        in_v_r3 <= 0;
        in_v_r4 <= 0;
        in_v_r5 <= 0;
        in_v_r6 <= 0;
        qin_r0  <= 0;
        qin_r1  <= 0;
        qin_r2  <= 0;
        qb_r0   <= 0;
        qc_r0   <= 0;
        qln2_r0 <= 0;
        qln2_inv_r0 <= 0;
        z_r1 <= 0;
        z_r2 <= 0;
        z_r3 <= 0;
        z_r4 <= 0;
        z_r5 <= 0;
        z_r6 <= 0;
        qp_r2 <= 0;
        qp_r3 <= 0;
        qp_r4 <= 0;
        ql_r4 <= 0;
        ql_r5 <= 0;
        ql_r6 <= 0;
        qout_r <= 0;
        done <= 0;
    end else if (enable) begin
        qb_r0       <= qb;
        qc_r0       <= qc;
        qln2_r0     <= qln2;
        qln2_inv_r0 <= qln2_inv;

        in_v_r0 <= in_valid;
        qin_r0  <= qin;

        z_r1p    <= fp_mul[D_W+24-1:FP_BITS];
        in_v_r1p <= in_v_r0;
        qin_r1p  <= qin_r0;

        z_r1    <= z_r1p;
        in_v_r1 <= in_v_r1p;
        qin_r1  <= qin_r1p;

        qp_r2p   <= z_r1 * qln2_r0;
        in_v_r2p <= in_v_r1;
        qin_r2p  <= qin_r1;
        z_r2p    <= (z_r1 > 2*D_W) ? 2*D_W : z_r1;

        qp_r2   <= qp_r2p;
        in_v_r2 <= in_v_r2p;
        qin_r2  <= qin_r2p;
        z_r2    <= z_r2p;

        qp_r3   <= qin_r2 - qp_r2;
        in_v_r3 <= in_v_r2;
        z_r3    <= z_r2;

        ql_r4   <= qp_r3 + qb_r0;
        qp_r4   <= qp_r3;
        in_v_r4 <= in_v_r3;
        z_r4    <= z_r3;

        ql_r5p  <= ql_r4 * qp_r4;
        in_v_r5p <= in_v_r4;
        z_r5p   <= z_r4;

        ql_r5  <= ql_r5p;
        in_v_r5 <= in_v_r5p;
        z_r5   <= z_r5p;

        ql_r6  <= ql_r5 + qc_r0;
        in_v_r6 <= in_v_r5;
        z_r6   <= z_r5;

        qout_r <= ql_r6 >> z_r6;
        done   <= in_v_r6;
    end
end

/* verilator lint_on WIDTHEXPAND */

endmodule
