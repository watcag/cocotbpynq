`timescale 1ns/1ps
// rp_finalize slot — GAMMA_LUT. 16-entry gamma 1/2.2 curve keyed on the
// top 4 bits of each channel. Brightens dark mid-tones while leaving
// extremes near unchanged. Exact integer values so the numpy reference
// can match bit-for-bit.
module finalize_rm (
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
    function [7:0] gamma_lut;
        input [7:0] c;
        begin
            case (c[7:4])
                4'h0: gamma_lut = 8'd0;
                4'h1: gamma_lut = 8'd64;
                4'h2: gamma_lut = 8'd91;
                4'h3: gamma_lut = 8'd111;
                4'h4: gamma_lut = 8'd128;
                4'h5: gamma_lut = 8'd142;
                4'h6: gamma_lut = 8'd155;
                4'h7: gamma_lut = 8'd167;
                4'h8: gamma_lut = 8'd179;
                4'h9: gamma_lut = 8'd189;
                4'hA: gamma_lut = 8'd199;
                4'hB: gamma_lut = 8'd209;
                4'hC: gamma_lut = 8'd218;
                4'hD: gamma_lut = 8'd227;
                4'hE: gamma_lut = 8'd236;
                4'hF: gamma_lut = 8'd245;
            endcase
        end
    endfunction

    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;
    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= {8'h00,
                              gamma_lut(s_axis_tdata[23:16]),
                              gamma_lut(s_axis_tdata[15: 8]),
                              gamma_lut(s_axis_tdata[ 7: 0])};
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
        end else if (m_axis_tvalid & m_axis_tready) m_axis_tvalid <= 1'b0;
    end
endmodule
