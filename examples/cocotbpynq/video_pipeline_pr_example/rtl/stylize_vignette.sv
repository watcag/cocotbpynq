`timescale 1ns/1ps
// rp_stylize slot — VIGNETTE. Darken pixels based on distance from the
// frame center. The thresholds are derived from W so the same RM works
// at any image size: max d^2 ≈ W^2/2 at the corners; we step the gain
// at W^2/64, W^2/16, W^2/8, W^2/4.
//
// For W = 64: thresholds = 64, 256, 512, 1024 (the original tuning).
// For W = 128: thresholds = 256, 1024, 2048, 4096.
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
    localparam signed [9:0] CENTER = $signed({2'b00, W[8:1]});  // W/2 zero-extended

    // Distance thresholds scale with W^2.
    localparam [19:0] D1 = (20'(W) * 20'(W)) >> 6;   // W^2/64
    localparam [19:0] D2 = (20'(W) * 20'(W)) >> 4;   // W^2/16
    localparam [19:0] D3 = (20'(W) * 20'(W)) >> 3;   // W^2/8
    localparam [19:0] D4 = (20'(W) * 20'(W)) >> 2;   // W^2/4

    reg [8:0] col;
    reg [8:0] row;

    wire signed [9:0] dx = $signed({1'b0, col}) - CENTER;
    wire signed [9:0] dy = $signed({1'b0, row}) - CENTER;
    wire [19:0] d2 = 20'(dx*dx) + 20'(dy*dy);

    reg [7:0] gain;
    always @(*) begin
        if      (d2 <  D1) gain = 8'd255;
        else if (d2 <  D2) gain = 8'd200;
        else if (d2 <  D3) gain = 8'd144;
        else if (d2 <  D4) gain = 8'd88;
        else               gain = 8'd32;
    end

    wire [7:0] r = s_axis_tdata[23:16];
    wire [7:0] g = s_axis_tdata[15: 8];
    wire [7:0] b = s_axis_tdata[ 7: 0];
    wire [15:0] r_scaled = r * gain;
    wire [15:0] g_scaled = g * gain;
    wire [15:0] b_scaled = b * gain;

    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;

    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= {8'h00, r_scaled[15:8], g_scaled[15:8], b_scaled[15:8]};
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
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
