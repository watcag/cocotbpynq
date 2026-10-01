`timescale 1ns/1ps
// Simplified AXI-Stream Switch — static routing via AXI-Lite.
// Register-compatible with Xilinx axis_switch (PG085, C_ROUTING_MODE=1):
//   0x00       : Control (bit 1 = commit)
//   0x40 + 4*i : MI_MUX[i] — which slave feeds master i (bit 31 = disable)

module axis_switch #(
    parameter NUM_PORTS   = 6,
    parameter TDATA_WIDTH = 32
) (
    input  wire                              aclk,
    input  wire                              aresetn,

    // AXI-Lite control interface
    input  wire [7:0]                        s_axi_ctrl_awaddr,
    input  wire                              s_axi_ctrl_awvalid,
    output reg                               s_axi_ctrl_awready,
    input  wire [31:0]                       s_axi_ctrl_wdata,
    input  wire [3:0]                        s_axi_ctrl_wstrb,
    input  wire                              s_axi_ctrl_wvalid,
    output reg                               s_axi_ctrl_wready,
    output wire [1:0]                        s_axi_ctrl_bresp,
    output reg                               s_axi_ctrl_bvalid,
    input  wire                              s_axi_ctrl_bready,
    input  wire [7:0]                        s_axi_ctrl_araddr,
    input  wire                              s_axi_ctrl_arvalid,
    output reg                               s_axi_ctrl_arready,
    output reg  [31:0]                       s_axi_ctrl_rdata,
    output wire [1:0]                        s_axi_ctrl_rresp,
    output reg                               s_axi_ctrl_rvalid,
    input  wire                              s_axi_ctrl_rready,

    // AXI-Stream slave ports (flattened: port 0 in LSBs)
    input  wire [NUM_PORTS*TDATA_WIDTH-1:0]  s_axis_tdata,
    input  wire [NUM_PORTS-1:0]              s_axis_tvalid,
    output wire [NUM_PORTS-1:0]              s_axis_tready,
    input  wire [NUM_PORTS-1:0]              s_axis_tlast,

    // AXI-Stream master ports (flattened: port 0 in LSBs)
    output wire [NUM_PORTS*TDATA_WIDTH-1:0]  m_axis_tdata,
    output wire [NUM_PORTS-1:0]              m_axis_tvalid,
    input  wire [NUM_PORTS-1:0]              m_axis_tready,
    output wire [NUM_PORTS-1:0]              m_axis_tlast
);

    assign s_axi_ctrl_bresp = 2'b00;
    assign s_axi_ctrl_rresp = 2'b00;

    // ── Routing registers (shadow written by SW, active after commit) ─────
    reg [31:0] mi_mux_shadow [0:NUM_PORTS-1];
    reg [31:0] mi_mux_active [0:NUM_PORTS-1];

    integer k;
    initial begin
        for (k = 0; k < NUM_PORTS; k = k + 1) begin
            mi_mux_shadow[k] = 32'h8000_0000;   // disabled
            mi_mux_active[k] = 32'h8000_0000;
        end
    end

    // ── AXI-Lite write channel ────────────────────────────────────────────
    reg [7:0] aw_addr;
    reg       aw_done, w_done;
    reg [31:0] w_data;

    always @(posedge aclk) begin
        if (!aresetn) begin
            s_axi_ctrl_awready <= 0;
            s_axi_ctrl_wready  <= 0;
            s_axi_ctrl_bvalid  <= 0;
            aw_done <= 0;
            w_done  <= 0;
        end else begin
            // Address accept
            if (s_axi_ctrl_awvalid && !aw_done) begin
                s_axi_ctrl_awready <= 1;
                aw_addr <= s_axi_ctrl_awaddr;
                aw_done <= 1;
            end else begin
                s_axi_ctrl_awready <= 0;
            end

            // Data accept
            if (s_axi_ctrl_wvalid && !w_done) begin
                s_axi_ctrl_wready <= 1;
                w_data <= s_axi_ctrl_wdata;
                w_done <= 1;
            end else begin
                s_axi_ctrl_wready <= 0;
            end

            // Process write when both phases complete
            if (aw_done && w_done && !s_axi_ctrl_bvalid) begin
                if (aw_addr == 8'h00 && w_data[1]) begin
                    // Commit: copy shadow → active
                    for (k = 0; k < NUM_PORTS; k = k + 1)
                        mi_mux_active[k] <= mi_mux_shadow[k];
                end else if (aw_addr >= 8'h40 && aw_addr < (8'h40 + 4 * NUM_PORTS)) begin
                    mi_mux_shadow[(aw_addr - 8'h40) >> 2] <= w_data;
                end
                s_axi_ctrl_bvalid <= 1;
                aw_done <= 0;
                w_done  <= 0;
            end

            // Response handshake
            if (s_axi_ctrl_bvalid && s_axi_ctrl_bready)
                s_axi_ctrl_bvalid <= 0;
        end
    end

    // ── AXI-Lite read channel ─────────────────────────────────────────────
    always @(posedge aclk) begin
        if (!aresetn) begin
            s_axi_ctrl_arready <= 0;
            s_axi_ctrl_rvalid  <= 0;
        end else begin
            if (s_axi_ctrl_arvalid && !s_axi_ctrl_rvalid) begin
                s_axi_ctrl_arready <= 1;
                s_axi_ctrl_rvalid  <= 1;
                if (s_axi_ctrl_araddr >= 8'h40 &&
                    s_axi_ctrl_araddr < (8'h40 + 4 * NUM_PORTS))
                    s_axi_ctrl_rdata <= mi_mux_active[(s_axi_ctrl_araddr - 8'h40) >> 2];
                else
                    s_axi_ctrl_rdata <= 32'h0;
            end else begin
                s_axi_ctrl_arready <= 0;
            end

            if (s_axi_ctrl_rvalid && s_axi_ctrl_rready)
                s_axi_ctrl_rvalid <= 0;
        end
    end

    // ── Crossbar: master data muxing ──────────────────────────────────────
    genvar mi;
    generate
        for (mi = 0; mi < NUM_PORTS; mi = mi + 1) begin : gen_mi
            wire        disabled = mi_mux_active[mi][31];
            wire [3:0]  si_sel   = mi_mux_active[mi][3:0];

            assign m_axis_tdata[mi*TDATA_WIDTH +: TDATA_WIDTH] =
                disabled ? {TDATA_WIDTH{1'b0}} :
                s_axis_tdata[si_sel * TDATA_WIDTH +: TDATA_WIDTH];

            assign m_axis_tvalid[mi] = disabled ? 1'b0 : s_axis_tvalid[si_sel];
            assign m_axis_tlast[mi]  = disabled ? 1'b0 : s_axis_tlast[si_sel];
        end
    endgenerate

    // ── Crossbar: slave ready — OR of all masters selecting this slave ────
    genvar si;
    generate
        for (si = 0; si < NUM_PORTS; si = si + 1) begin : gen_si
            wire [NUM_PORTS-1:0] connected;
            genvar j;
            for (j = 0; j < NUM_PORTS; j = j + 1) begin : gen_conn
                assign connected[j] = !mi_mux_active[j][31] &&
                                      (mi_mux_active[j][3:0] == si[3:0]);
            end
            assign s_axis_tready[si] = |(connected & m_axis_tready);
        end
    endgenerate

endmodule
