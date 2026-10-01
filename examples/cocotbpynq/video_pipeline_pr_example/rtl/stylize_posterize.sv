`timescale 1ns/1ps
// rp_stylize slot — POSTERIZE. Keep top KEEP_BITS of each channel; zero the rest.
// Default KEEP_BITS=5 → 32 levels per channel (~32k color palette).
module stylize_rm #(
    parameter integer KEEP_BITS = 5
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
    // Top KEEP_BITS set, rest cleared.  For KEEP_BITS=5 this is 0xF8.
    localparam [7:0] MASK = 8'(8'hFF << (8 - KEEP_BITS));

    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;
    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= {8'h00,
                              s_axis_tdata[23:16] & MASK,
                              s_axis_tdata[15: 8] & MASK,
                              s_axis_tdata[ 7: 0] & MASK};
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
        end else if (m_axis_tvalid & m_axis_tready) m_axis_tvalid <= 1'b0;
    end
endmodule
