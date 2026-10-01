`timescale 1ns/1ps
// rp_tone slot — BRIGHTEN. Saturating add OFFSET per channel.
// OFFSET is a Verilog parameter so the brightness step is tunable from YAML.
module tone_rm #(
    parameter [7:0] OFFSET = 8'd64
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
    function automatic [7:0] sat_addk (input [7:0] c);
        reg [8:0] s;
        begin s = {1'b0, c} + {1'b0, OFFSET}; sat_addk = s[8] ? 8'd255 : s[7:0]; end
    endfunction

    assign s_axis_tready = (!m_axis_tvalid) || m_axis_tready;
    wire transfer = s_axis_tvalid & s_axis_tready;
    always @(posedge clk) begin
        if (transfer) begin
            m_axis_tdata  <= {8'h00,
                              sat_addk(s_axis_tdata[23:16]),
                              sat_addk(s_axis_tdata[15: 8]),
                              sat_addk(s_axis_tdata[ 7: 0])};
            m_axis_tvalid <= 1'b1;
            m_axis_tlast  <= s_axis_tlast;
        end else if (m_axis_tvalid & m_axis_tready) m_axis_tvalid <= 1'b0;
    end
endmodule
