`timescale 1ns/1ps
// rp_finalize slot — GAIN. Saturating per-channel multiply by GAIN_Q0_8/256
// (Q0.8 fixed-point). Default 384 → 1.5x; pass GAIN_Q0_8=512 for 2x, etc.
module finalize_rm #(
    parameter [15:0] GAIN_Q0_8 = 16'd384
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
    function [7:0] gain_ch;
        input [7:0] c;
        reg [23:0] tmp;
        begin
            tmp = c * GAIN_Q0_8;
            tmp = tmp >> 8;
            gain_ch = (tmp > 24'd255) ? 8'd255 : tmp[7:0];
        end
    endfunction

    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;
    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= {8'h00,
                              gain_ch(s_axis_tdata[23:16]),
                              gain_ch(s_axis_tdata[15: 8]),
                              gain_ch(s_axis_tdata[ 7: 0])};
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
        end else if (m_axis_tvalid & m_axis_tready) m_axis_tvalid <= 1'b0;
    end
endmodule
