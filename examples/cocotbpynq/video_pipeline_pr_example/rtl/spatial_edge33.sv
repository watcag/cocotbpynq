`timescale 1ns/1ps
// rp_spatial slot — EDGE33. Sobel-X gradient magnitude per channel,
// saturated to [0, 255]. See spatial_blur33.sv for the timing and
// 3-bank line-buffer rotation convention.
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
    reg [23:0] lb [0:2] [0:W-1];
    reg [23:0] cur_m1, cur_m2;
    reg [1:0]  bank_top, bank_mid, bank_cur;

    wire [23:0] in_rgb = s_axis_tdata[23:0];
    wire [8:0]  col_m2 = (col <  9'd2) ? 9'd0 : col - 9'd2;

    wire [23:0] tl = lb[bank_top][col_m2];
    wire [23:0] tr = lb[bank_top][col];
    wire [23:0] ml = lb[bank_mid][col_m2];
    wire [23:0] mr = lb[bank_mid][col];
    wire [23:0] bl = cur_m2;
    wire [23:0] br = in_rgb;

    function [7:0] sobel_ch;
        input [7:0] c_tl, c_tr;
        input [7:0] c_ml, c_mr;
        input [7:0] c_bl, c_br;
        reg signed [12:0] gx;
        reg [12:0] mag;
        begin
            gx = $signed({5'd0, c_tr}) + ($signed({5'd0, c_mr}) <<< 1) + $signed({5'd0, c_br})
               - $signed({5'd0, c_tl}) - ($signed({5'd0, c_ml}) <<< 1) - $signed({5'd0, c_bl});
            mag = (gx < 13'sd0) ? 13'(-gx) : 13'(gx);
            sobel_ch = (mag > 13'd255) ? 8'd255 : mag[7:0];
        end
    endfunction

    wire [7:0] fr = sobel_ch(tl[23:16], tr[23:16],
                             ml[23:16], mr[23:16],
                             bl[23:16], br[23:16]);
    wire [7:0] fg = sobel_ch(tl[15: 8], tr[15: 8],
                             ml[15: 8], mr[15: 8],
                             bl[15: 8], br[15: 8]);
    wire [7:0] fb = sobel_ch(tl[ 7: 0], tr[ 7: 0],
                             ml[ 7: 0], mr[ 7: 0],
                             bl[ 7: 0], br[ 7: 0]);

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
