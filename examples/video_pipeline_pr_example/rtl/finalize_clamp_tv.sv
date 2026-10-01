`timescale 1ns/1ps
// rp_finalize slot — CLAMP_TV. Clip every channel into [LO, HI].
// Default [16, 240] is BT.601 limited-range, per-channel.
module finalize_rm #(
    parameter [7:0] LO = 8'd16,
    parameter [7:0] HI = 8'd240
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
    function [7:0] clamp_tv;
        input [7:0] c;
        begin
            if (c < LO)      clamp_tv = LO;
            else if (c > HI) clamp_tv = HI;
            else             clamp_tv = c;
        end
    endfunction

    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;
    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= {8'h00,
                              clamp_tv(s_axis_tdata[23:16]),
                              clamp_tv(s_axis_tdata[15: 8]),
                              clamp_tv(s_axis_tdata[ 7: 0])};
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
        end else if (m_axis_tvalid & m_axis_tready) m_axis_tvalid <= 1'b0;
    end
endmodule
