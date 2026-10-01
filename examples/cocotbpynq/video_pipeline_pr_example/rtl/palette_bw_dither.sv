`timescale 1ns/1ps
// rp_palette slot — BW_DITHER. 2×2 Bayer dither into B&W, advanced once
// per accepted pixel via the AXI-Stream handshake.
module palette_rm (
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
    reg [1:0] cnt;

    wire [7:0] r = s_axis_tdata[23:16];
    wire [7:0] g = s_axis_tdata[15: 8];
    wire [7:0] b = s_axis_tdata[ 7: 0];
    wire [15:0] y_full = 16'd77 * r + 16'd150 * g + 16'd29 * b;
    wire [7:0]  y      = y_full[15:8];

    reg [7:0] thresh;
    always @(*) begin
        case (cnt)
            2'd0: thresh = 8'd64;
            2'd1: thresh = 8'd192;
            2'd2: thresh = 8'd128;
            default: thresh = 8'd0;
        endcase
    end

    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;

    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= (y > thresh) ? 32'h00FFFFFF : 32'h00000000;
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
            cnt <= s_axis_tlast ? 2'd0 : (cnt + 2'd1);
        end else if (m_axis_tvalid & m_axis_tready) begin
            m_axis_tvalid <= 1'b0;
        end
    end
endmodule
