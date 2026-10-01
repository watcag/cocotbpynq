`timescale 1ns/1ps
// Static region for the AXI PR example.
//
// Exposes two AXI-Lite registers to cocotbpynq / PYNQ MMIO:
//   0x00  data_in   (R/W) - written by PS, forwarded to reconfigurable module
//   0x04  result    (R)   - output from reconfigurable module, read by PS
//
// The reconfigurable partition (rp_compute) is instantiated inline here.
// At build time the framework replaces that instantiation with a DPI bridge
// connected to the separate RM Verilator process.
//
// AXI-Lite port naming convention used by HwhGenerator:
//   {interface_name}_{signal}   e.g.  ctrl_awaddr, ctrl_rdata, ...

module compute_static (
    input  wire        clk,
    input  wire        rst_n,

    // AXI-Lite slave – prefix 'ctrl'
    input  wire [31:0] ctrl_awaddr,
    input  wire        ctrl_awvalid,
    output reg         ctrl_awready,

    input  wire [31:0] ctrl_wdata,
    input  wire [3:0]  ctrl_wstrb,
    input  wire        ctrl_wvalid,
    output reg         ctrl_wready,

    output reg  [1:0]  ctrl_bresp,
    output reg         ctrl_bvalid,
    input  wire        ctrl_bready,

    input  wire [31:0] ctrl_araddr,
    input  wire        ctrl_arvalid,
    output reg         ctrl_arready,

    output reg  [31:0] ctrl_rdata,
    output reg  [1:0]  ctrl_rresp,
    output reg         ctrl_rvalid,
    input  wire        ctrl_rready
);

    // ── internal registers ────────────────────────────────────────────────
    reg [31:0] data_in_reg;
    wire [31:0] result_wire;   // driven by rp_compute DPI bridge

    // ── AXI-Lite write: independent address & data capture ──────────────
    // cocotbpynq sends address then data sequentially (per AXI-Lite spec).
    // We latch each independently and commit when both have arrived.
    reg        aw_received;
    reg [31:0] aw_addr_latched;
    reg        w_received;
    reg [31:0] w_data_latched;
    reg [3:0]  w_strb_latched;

    always @(posedge clk) begin
        if (!rst_n) begin
            ctrl_awready    <= 1'b0;
            ctrl_wready     <= 1'b0;
            ctrl_bvalid     <= 1'b0;
            ctrl_bresp      <= 2'b00;
            data_in_reg     <= 32'h0;
            aw_received     <= 1'b0;
            aw_addr_latched <= 32'h0;
            w_received      <= 1'b0;
            w_data_latched  <= 32'h0;
            w_strb_latched  <= 4'h0;
        end else begin
            // Default: ready to accept unless already latched
            ctrl_awready <= ~aw_received;
            ctrl_wready  <= ~w_received;

            // Latch address when valid & ready
            if (ctrl_awvalid && !aw_received) begin
                aw_addr_latched <= ctrl_awaddr;
                aw_received     <= 1'b1;
                ctrl_awready    <= 1'b0;
            end

            // Latch data when valid & ready
            if (ctrl_wvalid && !w_received) begin
                w_data_latched <= ctrl_wdata;
                w_strb_latched <= ctrl_wstrb;
                w_received     <= 1'b1;
                ctrl_wready    <= 1'b0;
            end

            // Commit write when both arrived
            if (aw_received && w_received && !ctrl_bvalid) begin
                case (aw_addr_latched[3:0])
                    4'h0: begin
                        if (w_strb_latched[0]) data_in_reg[ 7: 0] <= w_data_latched[ 7: 0];
                        if (w_strb_latched[1]) data_in_reg[15: 8] <= w_data_latched[15: 8];
                        if (w_strb_latched[2]) data_in_reg[23:16] <= w_data_latched[23:16];
                        if (w_strb_latched[3]) data_in_reg[31:24] <= w_data_latched[31:24];
                    end
                    default: ; // ignore writes to unknown addresses
                endcase
                ctrl_bvalid  <= 1'b1;
                ctrl_bresp   <= 2'b00;
                aw_received  <= 1'b0;
                w_received   <= 1'b0;
            end

            // Clear response when master accepts it
            if (ctrl_bready && ctrl_bvalid) begin
                ctrl_bvalid <= 1'b0;
            end
        end
    end

    // ── AXI-Lite read path ────────────────────────────────────────────────
    always @(posedge clk) begin
        if (!rst_n) begin
            ctrl_arready <= 1'b0;
            ctrl_rvalid  <= 1'b0;
            ctrl_rdata   <= 32'h0;
            ctrl_rresp   <= 2'b00;
        end else begin
            // Accept address when no read response pending
            ctrl_arready <= ~ctrl_rvalid;

            if (ctrl_arvalid && ctrl_arready) begin
                ctrl_rvalid  <= 1'b1;
                ctrl_rresp   <= 2'b00;
                case (ctrl_araddr[3:0])
                    4'h0: ctrl_rdata <= data_in_reg;
                    4'h4: ctrl_rdata <= result_wire;
                    default: ctrl_rdata <= 32'hDEAD_BEEF;
                endcase
            end else if (ctrl_rready && ctrl_rvalid) begin
                ctrl_rvalid <= 1'b0;
            end
        end
    end

    // ── Reconfigurable partition rp_compute ──────────────────────────────
    // Replaced by DPI bridge at build time.
    // data_in → RM input; RM output → result_wire
    compute_rm u_compute_rm (
        .clk     (clk),
        .data_in (data_in_reg),
        .result  (result_wire)
    );

endmodule
