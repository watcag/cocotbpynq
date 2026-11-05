// AXI4-Stream adapters for the NoC interconnect (noc_interconnect: true).
//
// The stream NoC carries 128-, 256- or 512-bit TDATA; pynq-pr modules stream 32-bit words. Each
// word travels alone in a 128-bit NoC beat: noc_stream_tx zero-extends it and tags it with the
// destination (TDEST), noc_stream_narrow keeps the low word. TLAST and the handshake pass through.
// noc_stream_tx takes dest at the first beat of a packet and holds it until TLAST, so a route
// written mid-packet applies from the next packet (as the AXI4-Stream switch applies a commit).

module noc_stream_tx #(
    parameter DATA_W = 32,
    parameter NOC_W  = 128,
    parameter DEST_W = 2
) (
    input  wire              clk,
    input  wire              resetn,
    input  wire [DEST_W-1:0] dest,
    input  wire [DATA_W-1:0] s_axis_tdata,
    input  wire              s_axis_tvalid,
    output wire              s_axis_tready,
    input  wire              s_axis_tlast,
    output wire [NOC_W-1:0]  m_axis_tdata,
    output wire              m_axis_tvalid,
    input  wire              m_axis_tready,
    output wire              m_axis_tlast,
    output wire [DEST_W-1:0] m_axis_tdest
);
    assign m_axis_tdata  = {{(NOC_W - DATA_W){1'b0}}, s_axis_tdata};
    assign m_axis_tvalid = s_axis_tvalid;
    assign s_axis_tready = m_axis_tready;
    assign m_axis_tlast  = s_axis_tlast;
    reg              in_packet;
    reg [DEST_W-1:0] packet_dest;
    always @(posedge clk) begin
        if (!resetn) begin
            in_packet <= 1'b0;
        end else if (s_axis_tvalid && m_axis_tready) begin
            if (!in_packet) packet_dest <= dest;
            in_packet <= !s_axis_tlast;
        end
    end
    assign m_axis_tdest  = in_packet ? packet_dest : dest;
endmodule

module noc_stream_narrow #(
    parameter DATA_W = 32,
    parameter NOC_W  = 128
) (
    input  wire              clk,
    input  wire [NOC_W-1:0]  s_axis_tdata,
    input  wire              s_axis_tvalid,
    output wire              s_axis_tready,
    input  wire              s_axis_tlast,
    output wire [DATA_W-1:0] m_axis_tdata,
    output wire              m_axis_tvalid,
    input  wire              m_axis_tready,
    output wire              m_axis_tlast
);
    assign m_axis_tdata  = s_axis_tdata[DATA_W-1:0];
    assign m_axis_tvalid = s_axis_tvalid;
    assign s_axis_tready = m_axis_tready;
    assign m_axis_tlast  = s_axis_tlast;
endmodule
