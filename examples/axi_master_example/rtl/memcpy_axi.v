`timescale 1ns / 1ps
// memcpy_axi: an AXI4 master that copies LEN bytes from SRC to DST in PS DDR (the example of
// cocotbpynq.axi_mem: a PL master reading and writing the buffers through an HP port).
//
// AXI4-Lite registers (32-bit):
//   0x00 CTRL    W   bit0 start (pulse), bit1 clear DONE
//   0x04 STATUS  R   bit0 busy, bit1 done (sticky until CTRL bit1 or the next start), bit2 error (a bad response)
//   0x10 SRC_LO  RW  0x14 SRC_HI
//   0x18 DST_LO  RW  0x1C DST_HI
//   0x20 LEN     RW  bytes, a multiple of 128 (whole 16-beat bursts of 8 bytes)
//   0x24 IDMODE  RW  bit0: read bursts alternate ARID 0 / 1 (so a slave may return them out of order)
//   0x28 BURSTS  R   bursts written since the start
//
// Data path: up to NSLOT read bursts in flight, each into its own slot of a burst buffer. A
// finished slot (RLAST) queues for writing in completion order; its AW and W beats go out and
// the slot is free again at its B. Read data of one burst arrives without interleaving with
// another ID's burst (the slave finishes a started burst first, as cocotbpynq.axi_mem does).
module memcpy_axi #(
    parameter integer AW = 40,
    parameter integer NSLOT = 4
) (
    input  wire          clk,
    input  wire          resetn,
    // AXI4-Lite slave
    input  wire [7:0]    s_axi_awaddr, input wire s_axi_awvalid, output reg s_axi_awready,
    input  wire [31:0]   s_axi_wdata, input wire [3:0] s_axi_wstrb, input wire s_axi_wvalid, output reg s_axi_wready,
    output wire [1:0]    s_axi_bresp, output reg s_axi_bvalid, input wire s_axi_bready,
    input  wire [7:0]    s_axi_araddr, input wire s_axi_arvalid, output reg s_axi_arready,
    output reg  [31:0]   s_axi_rdata, output wire [1:0] s_axi_rresp, output reg s_axi_rvalid, input wire s_axi_rready,
    // AXI4 master
    output wire [1:0]    m_axi_arid,   output wire [AW-1:0] m_axi_araddr, output wire [7:0] m_axi_arlen,
    output wire [2:0]    m_axi_arsize, output wire [1:0] m_axi_arburst, output reg m_axi_arvalid,
    input  wire          m_axi_arready,
    input  wire [1:0]    m_axi_rid,    input wire [63:0] m_axi_rdata, input wire [1:0] m_axi_rresp,
    input  wire          m_axi_rlast,  input wire m_axi_rvalid, output wire m_axi_rready,
    output wire [1:0]    m_axi_awid,   output wire [AW-1:0] m_axi_awaddr, output wire [7:0] m_axi_awlen,
    output wire [2:0]    m_axi_awsize, output wire [1:0] m_axi_awburst, output reg m_axi_awvalid,
    input  wire          m_axi_awready,
    output wire [63:0]   m_axi_wdata,  output wire [7:0] m_axi_wstrb, output wire m_axi_wlast, output reg m_axi_wvalid,
    input  wire          m_axi_wready,
    input  wire [1:0]    m_axi_bid,    input wire [1:0] m_axi_bresp, input wire m_axi_bvalid, output wire m_axi_bready
);
    localparam integer BEATS = 16, BBYTES = 8 * BEATS;
    wire rst = !resetn;

    // ---------------------------------------------------------------- registers
    reg [63:0] src, dst;
    reg [31:0] len;
    reg        idmode, busy, done, err;
    reg [31:0] nbursts;
    reg        start_p, clear_p;
    always @(posedge clk) begin
        start_p <= 1'b0; clear_p <= 1'b0;
        if (rst) begin
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0; s_axi_bvalid <= 1'b0;
            src <= 0; dst <= 0; len <= 0; idmode <= 1'b0;
        end else begin
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0;
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
            if (s_axi_awvalid && s_axi_wvalid && !s_axi_bvalid && !s_axi_awready) begin
                s_axi_awready <= 1'b1; s_axi_wready <= 1'b1; s_axi_bvalid <= 1'b1;
                case (s_axi_awaddr)
                    8'h00: begin start_p <= s_axi_wdata[0]; clear_p <= s_axi_wdata[1]; end
                    8'h10: src[31:0] <= s_axi_wdata;
                    8'h14: src[63:32] <= s_axi_wdata;
                    8'h18: dst[31:0] <= s_axi_wdata;
                    8'h1C: dst[63:32] <= s_axi_wdata;
                    8'h20: len <= s_axi_wdata;
                    8'h24: idmode <= s_axi_wdata[0];
                    default: ;
                endcase
            end
        end
    end
    assign s_axi_bresp = 2'b00;
    assign s_axi_rresp = 2'b00;
    always @(posedge clk) begin
        if (rst) begin
            s_axi_arready <= 1'b0; s_axi_rvalid <= 1'b0;
        end else begin
            s_axi_arready <= 1'b0;
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
            if (s_axi_arvalid && !s_axi_rvalid && !s_axi_arready) begin
                s_axi_arready <= 1'b1; s_axi_rvalid <= 1'b1;
                case (s_axi_araddr)
                    8'h04: s_axi_rdata <= {29'd0, err, done, busy};
                    8'h10: s_axi_rdata <= src[31:0];
                    8'h14: s_axi_rdata <= src[63:32];
                    8'h18: s_axi_rdata <= dst[31:0];
                    8'h1C: s_axi_rdata <= dst[63:32];
                    8'h20: s_axi_rdata <= len;
                    8'h24: s_axi_rdata <= {31'd0, idmode};
                    8'h28: s_axi_rdata <= nbursts;
                    default: s_axi_rdata <= 32'hDEADBEEF;
                endcase
            end
        end
    end

    // ---------------------------------------------------------------- slots
    reg [63:0] buffer [0:NSLOT*BEATS-1];
    reg [NSLOT-1:0] used;                       // a read is in flight or the slot waits to be written / for its B
    reg [31:0] slot_off [0:NSLOT-1];
    reg [4:0]  rbeat [0:NSLOT-1];
    // rings (head / tail, NSLOT = 4 entries): per ID the slots of its read bursts in flight (AR order); the slots
    // ready to write (completion order); the slots whose B is pending (AW order)
    reg [1:0]  idq [0:1][0:NSLOT-1];
    reg [1:0]  idq_h [0:1], idq_t [0:1];
    reg [1:0]  wq [0:NSLOT-1];
    reg [1:0]  wq_h, wq_t;
    reg [2:0]  wq_n;
    reg [1:0]  bq [0:NSLOT-1];
    reg [1:0]  bq_h, bq_t;
    reg [31:0] rd_off;
    reg        burst_par;

    // lowest free slot
    reg [1:0] free_slot; reg have_free;
    integer k;
    always @(*) begin
        have_free = 1'b0; free_slot = 2'd0;
        for (k = NSLOT - 1; k >= 0; k = k - 1)
            if (!used[k]) begin have_free = 1'b1; free_slot = k[1:0]; end
    end

    // AR
    reg [1:0]  ar_slot;
    reg [AW-1:0] araddr_r;
    reg [1:0]  arid_r;
    assign m_axi_araddr = araddr_r;
    assign m_axi_arid = arid_r;
    assign m_axi_arlen = 8'd15;
    assign m_axi_arsize = 3'd3;
    assign m_axi_arburst = 2'b01;
    assign m_axi_rready = 1'b1;
    // AW / W of the head of wq
    reg        aw_done, w_active;
    reg [4:0]  wbeat;
    wire [1:0] wslot = wq[wq_h];
    assign m_axi_awid = 2'd0;
    assign m_axi_awaddr = dst[AW-1:0] + {{(AW-32){1'b0}}, slot_off[wslot]};
    assign m_axi_awlen = 8'd15;
    assign m_axi_awsize = 3'd3;
    assign m_axi_awburst = 2'b01;
    assign m_axi_wdata = buffer[{wslot, wbeat[3:0]}];
    assign m_axi_wstrb = 8'hFF;
    assign m_axi_wlast = wbeat == 5'd15;
    assign m_axi_bready = 1'b1;

    wire [1:0] rslot = idq[m_axi_rid[0]][idq_h[m_axi_rid[0]]];
    // the slot is written once its last W beat and its AW are taken; it is queued for its B in that same cycle,
    // since the B may follow the last W beat in the next cycle
    reg        w_done;
    wire       w_fin = w_active && (w_done || (m_axi_wvalid && m_axi_wready && m_axi_wlast))
                                && (aw_done || (m_axi_awvalid && m_axi_awready));
    always @(posedge clk) begin
        if (rst || start_p) begin
            used <= 0; idq_h[0] <= 0; idq_t[0] <= 0; idq_h[1] <= 0; idq_t[1] <= 0;
            wq_h <= 0; wq_t <= 0; wq_n <= 0; bq_h <= 0; bq_t <= 0; rd_off <= 0; burst_par <= 1'b0;
            m_axi_arvalid <= 1'b0; m_axi_awvalid <= 1'b0; m_axi_wvalid <= 1'b0; aw_done <= 1'b0; w_active <= 1'b0; w_done <= 1'b0;
            wbeat <= 0; nbursts <= 0; err <= 1'b0;
            busy <= !rst && start_p; done <= 1'b0;
        end else begin
            if (clear_p) done <= 1'b0;
            // ---- AR: one burst into a free slot
            if (m_axi_arvalid && m_axi_arready) begin
                m_axi_arvalid <= 1'b0;
                idq[arid_r[0]][idq_t[arid_r[0]]] <= ar_slot;
                idq_t[arid_r[0]] <= idq_t[arid_r[0]] + 1;
            end
            if (busy && !m_axi_arvalid && rd_off < len && have_free) begin
                m_axi_arvalid <= 1'b1;
                araddr_r <= src[AW-1:0] + {{(AW-32){1'b0}}, rd_off};
                arid_r <= idmode ? {1'b0, burst_par} : 2'd0;
                burst_par <= !burst_par;
                ar_slot <= free_slot;
                used[free_slot] <= 1'b1;
                slot_off[free_slot] <= rd_off;
                rbeat[free_slot] <= 0;
                rd_off <= rd_off + BBYTES;
            end
            // ---- R: into the slot at the head of the beat's ID ring
            if (m_axi_rvalid) begin
                buffer[{rslot, rbeat[rslot][3:0]}] <= m_axi_rdata;
                rbeat[rslot] <= rbeat[rslot] + 1;
                if (m_axi_rresp != 2'b00) err <= 1'b1;
                if (m_axi_rlast) begin
                    idq_h[m_axi_rid[0]] <= idq_h[m_axi_rid[0]] + 1;
                    wq[wq_t] <= rslot;
                    wq_t <= wq_t + 1;
                end
            end
            // ---- AW and W of the slot at the head of wq
            if (wq_n != 0 && !w_active) begin
                w_active <= 1'b1; m_axi_awvalid <= 1'b1; m_axi_wvalid <= 1'b1; aw_done <= 1'b0; w_done <= 1'b0; wbeat <= 0;
            end
            if (m_axi_awvalid && m_axi_awready) begin m_axi_awvalid <= 1'b0; aw_done <= 1'b1; end
            if (m_axi_wvalid && m_axi_wready) begin
                wbeat <= wbeat + 1;
                if (m_axi_wlast) begin m_axi_wvalid <= 1'b0; w_done <= 1'b1; end
            end
            // the slot is written: it waits for its B
            if (w_fin) begin
                w_active <= 1'b0;
                wq_h <= wq_h + 1;
                bq[bq_t] <= wslot;
                bq_t <= bq_t + 1;
            end
            wq_n <= wq_n + ((m_axi_rvalid && m_axi_rlast) ? 3'd1 : 3'd0) - (w_fin ? 3'd1 : 3'd0);
            // ---- B: frees the oldest written slot
            if (m_axi_bvalid) begin
                used[bq[bq_h]] <= 1'b0;
                bq_h <= bq_h + 1;
                nbursts <= nbursts + 1;
                if (m_axi_bresp != 2'b00) err <= 1'b1;
            end
            // ---- done: everything read, written and acknowledged
            if (busy && rd_off >= len && used == 0 && !m_axi_arvalid) begin
                busy <= 1'b0; done <= 1'b1;
            end
        end
    end
endmodule
