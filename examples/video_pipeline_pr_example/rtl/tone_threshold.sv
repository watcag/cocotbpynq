`timescale 1ns/1ps
// rp_tone slot — THRESHOLD. Y > THRESH → white, else black.
module tone_rm #(
    parameter [7:0] THRESH = 8'd128
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
    wire [7:0] r = s_axis_tdata[23:16];
    wire [7:0] g = s_axis_tdata[15: 8];
    wire [7:0] b = s_axis_tdata[ 7: 0];
    wire [15:0] y_full = 16'd77 * r + 16'd150 * g + 16'd29 * b;
    wire [7:0]  y      = y_full[15:8];

    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;
    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= (y > THRESH) ? 32'h00FFFFFF : 32'h00000000;
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
        end else if (m_axis_tvalid & m_axis_tready) m_axis_tvalid <= 1'b0;
    end
endmodule
