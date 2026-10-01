`timescale 1ns/1ps
// rp_color slot — SEPIA. 3x3 matrix in Q0.8 fixed point with saturation.
//   R' = sat(( 99·R + 196·G +  47·B) >> 8)
//   G' = sat(( 87·R + 175·G +  42·B) >> 8)
//   B' = sat(( 68·R + 137·G +  33·B) >> 8)
module color_rm (
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
    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;

    wire [7:0] r = s_axis_tdata[23:16];
    wire [7:0] g = s_axis_tdata[15: 8];
    wire [7:0] b = s_axis_tdata[ 7: 0];

    // 18-bit accumulator (max value (99+196+47)*255 = 87210 fits in 17 bits).
    wire [17:0] r_acc = 18'd99  * {10'd0, r} + 18'd196 * {10'd0, g} + 18'd47 * {10'd0, b};
    wire [17:0] g_acc = 18'd87  * {10'd0, r} + 18'd175 * {10'd0, g} + 18'd42 * {10'd0, b};
    wire [17:0] b_acc = 18'd68  * {10'd0, r} + 18'd137 * {10'd0, g} + 18'd33 * {10'd0, b};

    // Top 10 bits hold the integer portion after >>8. Saturate to 255.
    wire [9:0] r_shift = r_acc[17:8];
    wire [9:0] g_shift = g_acc[17:8];
    wire [9:0] b_shift = b_acc[17:8];

    wire [7:0] r_out = (r_shift > 10'd255) ? 8'd255 : r_shift[7:0];
    wire [7:0] g_out = (g_shift > 10'd255) ? 8'd255 : g_shift[7:0];
    wire [7:0] b_out = (b_shift > 10'd255) ? 8'd255 : b_shift[7:0];

    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= {8'h00, r_out, g_out, b_out};
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
        end else if (m_axis_tvalid & m_axis_tready) begin
            m_axis_tvalid <= 1'b0;
        end
    end
endmodule
