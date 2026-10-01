`timescale 1ns/1ps
// rp_spatial slot — BLUR33. Gaussian-ish 3x3 kernel [1 2 1 / 2 4 2 / 1 2 1]
// divided by 16, applied per channel. Image width W is a Verilog
// parameter passed in from the YAML config. Output is shifted by
// (+1 col, +1 row) in the stream: when input pixel (col, row) is
// accepted, the filtered value centered at (col-1, row-1) is emitted
// iff (col >= 2 AND row >= 2); otherwise the input pixel is passed
// through.
//
// Three rotating line-buffer banks (indexed by row mod 3) keep the
// previous two rows stable for the full duration of the current row:
//   bank_top = (row+1) mod 3   — pixels from row-2
//   bank_mid = (row+2) mod 3   — pixels from row-1
//   bank_cur = (row    ) mod 3 — pixels from current row (being written)
module spatial_rm #(
    parameter [8:0] W = 9'd128
) (
    input  wire        clk,
    input  wire [31:0] s_axis_tdata,
    input  wire        s_axis_tvalid,
    input  wire        s_axis_tlast,
    output wire        s_axis_tready,
    input  wire        m_axis_tready,
    output reg  [31:0] m_axis_tdata,
    output reg         m_axis_tvalid,
    output reg         m_axis_tlast
);
    reg [8:0]  col;
    reg [8:0]  row;
    reg [23:0] lb [0:2] [0:W-1];   // 3-bank rotating line buffer (W deep)
    reg [23:0] cur_m1, cur_m2;
    reg [1:0]  bank_top, bank_mid, bank_cur;

    wire [23:0] in_rgb = s_axis_tdata[23:0];
    wire [8:0]  col_m1 = (col == 9'd0) ? 9'd0 : col - 9'd1;
    wire [8:0]  col_m2 = (col <  9'd2) ? 9'd0 : col - 9'd2;

    wire [23:0] tl = lb[bank_top][col_m2];
    wire [23:0] tm = lb[bank_top][col_m1];
    wire [23:0] tr = lb[bank_top][col];
    wire [23:0] ml = lb[bank_mid][col_m2];
    wire [23:0] mm = lb[bank_mid][col_m1];
    wire [23:0] mr = lb[bank_mid][col];
    wire [23:0] bl = cur_m2;
    wire [23:0] bm = cur_m1;
    wire [23:0] br = in_rgb;

    function [7:0] blur_ch;
        input [7:0] a_tl, a_tm, a_tr;
        input [7:0] a_ml, a_mm, a_mr;
        input [7:0] a_bl, a_bm, a_br;
        reg   [11:0] sum;
        begin
            sum = {4'd0, a_tl} + ({4'd0, a_tm} << 1) + {4'd0, a_tr}
                + ({4'd0, a_ml} << 1) + ({4'd0, a_mm} << 2) + ({4'd0, a_mr} << 1)
                + {4'd0, a_bl} + ({4'd0, a_bm} << 1) + {4'd0, a_br};
            blur_ch = sum[11:4]; // /16
        end
    endfunction

    wire [7:0] fr = blur_ch(tl[23:16], tm[23:16], tr[23:16],
                            ml[23:16], mm[23:16], mr[23:16],
                            bl[23:16], bm[23:16], br[23:16]);
    wire [7:0] fg = blur_ch(tl[15: 8], tm[15: 8], tr[15: 8],
                            ml[15: 8], mm[15: 8], mr[15: 8],
                            bl[15: 8], bm[15: 8], br[15: 8]);
    wire [7:0] fb = blur_ch(tl[ 7: 0], tm[ 7: 0], tr[ 7: 0],
                            ml[ 7: 0], mm[ 7: 0], mr[ 7: 0],
                            bl[ 7: 0], bm[ 7: 0], br[ 7: 0]);

    wire warmed = (row >= 9'd2) && (col >= 9'd2);
    wire [31:0] out_pix = warmed ? {8'h00, fr, fg, fb} : s_axis_tdata;

    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;

    initial begin
        bank_top = 2'd1;
        bank_mid = 2'd2;
        bank_cur = 2'd0;
    end

    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= out_pix;
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
            lb[bank_cur][col] <= in_rgb;
            cur_m2 <= cur_m1;
            cur_m1 <= in_rgb;
            if (s_axis_tlast) begin
                col <= 9'd0;
                row <= 9'd0;
                bank_top <= 2'd1;
                bank_mid <= 2'd2;
                bank_cur <= 2'd0;
            end else if (col == W-9'd1) begin
                col <= 9'd0;
                row <= row + 9'd1;
                bank_top <= bank_mid;
                bank_mid <= bank_cur;
                bank_cur <= bank_top;
            end else begin
                col <= col + 9'd1;
            end
        end else if (m_axis_tvalid & m_axis_tready) m_axis_tvalid <= 1'b0;
    end
endmodule
