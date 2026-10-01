`timescale 1ns/1ps
// rp_stylize slot — PIXELATE. 2x2 block replication driven by the
// AXI-Stream handshake. We latch the pixel value at (even_col, even_row)
// and replay it for (odd_col, even_row), (even_col, odd_row),
// (odd_col, odd_row). State advances exactly once per accepted pixel.
module stylize_rm #(
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
    reg [8:0] col;
    reg [8:0] row;
    // Per-column latch of the top-left pixel of the current 2x2 block.
    reg [31:0] top_row_lb [0:W-1];

    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;

    wire [31:0] out_pix = (row[0] == 1'b0)
                          ? (col[0] == 1'b0 ? s_axis_tdata : top_row_lb[col-9'd1])
                          : (col[0] == 1'b0 ? top_row_lb[col]   : top_row_lb[col-9'd1]);

    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= out_pix;
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
            if (row[0] == 1'b0 && col[0] == 1'b0)
                top_row_lb[col] <= s_axis_tdata;
            if (s_axis_tlast) begin
                col <= 9'd0;
                row <= 9'd0;
            end else if (col == W-9'd1) begin
                col <= 9'd0;
                row <= row + 9'd1;
            end else begin
                col <= col + 9'd1;
            end
        end else if (m_axis_tvalid & m_axis_tready) m_axis_tvalid <= 1'b0;
    end
endmodule
