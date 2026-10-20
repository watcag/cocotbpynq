// s2mm (ap_ctrl_hs): writes n 32-bit words from the in stream to dst (AXI4 master, one beat per burst).
// Registers: 0x00 control (ap_start, ap_done (clear on read), ap_idle, ap_ready), 0x10/0x14 dst, 0x1c n.
module s2mm (
    input  wire        ap_clk,
    input  wire        ap_rst_n,
    // AXI4 master (write only; the read channels are tied off)
    output wire        m_axi_gmem_ARVALID,
    input  wire        m_axi_gmem_ARREADY,
    output wire [63:0] m_axi_gmem_ARADDR,
    output wire [7:0]  m_axi_gmem_ARLEN,
    output wire [2:0]  m_axi_gmem_ARSIZE,
    output wire [1:0]  m_axi_gmem_ARBURST,
    input  wire        m_axi_gmem_RVALID,
    output wire        m_axi_gmem_RREADY,
    input  wire [31:0] m_axi_gmem_RDATA,
    input  wire        m_axi_gmem_RLAST,
    input  wire [1:0]  m_axi_gmem_RRESP,
    output reg         m_axi_gmem_AWVALID,
    input  wire        m_axi_gmem_AWREADY,
    output wire [63:0] m_axi_gmem_AWADDR,
    output wire [7:0]  m_axi_gmem_AWLEN,
    output wire [2:0]  m_axi_gmem_AWSIZE,
    output wire [1:0]  m_axi_gmem_AWBURST,
    output reg         m_axi_gmem_WVALID,
    input  wire        m_axi_gmem_WREADY,
    output wire [31:0] m_axi_gmem_WDATA,
    output wire [3:0]  m_axi_gmem_WSTRB,
    output wire        m_axi_gmem_WLAST,
    input  wire        m_axi_gmem_BVALID,
    output wire        m_axi_gmem_BREADY,
    input  wire [1:0]  m_axi_gmem_BRESP,
    // AXI4-Stream in
    input  wire [31:0] in_TDATA,
    input  wire        in_TVALID,
    output wire        in_TREADY,
    input  wire        in_TLAST,
    // AXI4-Lite control
    input  wire [5:0]  s_axi_control_AWADDR,
    input  wire        s_axi_control_AWVALID,
    output wire        s_axi_control_AWREADY,
    input  wire [31:0] s_axi_control_WDATA,
    input  wire [3:0]  s_axi_control_WSTRB,
    input  wire        s_axi_control_WVALID,
    output wire        s_axi_control_WREADY,
    output wire [1:0]  s_axi_control_BRESP,
    output wire        s_axi_control_BVALID,
    input  wire        s_axi_control_BREADY,
    input  wire [5:0]  s_axi_control_ARADDR,
    input  wire        s_axi_control_ARVALID,
    output wire        s_axi_control_ARREADY,
    output wire [31:0] s_axi_control_RDATA,
    output wire [1:0]  s_axi_control_RRESP,
    output wire        s_axi_control_RVALID,
    input  wire        s_axi_control_RREADY
);
  localparam IDLE = 0, RECV = 1, WRITE = 2, RESP = 3;
  reg [1:0] state;
  reg start, done;
  reg [63:0] dst;
  reg [31:0] n, i, word;
  wire wr, rd;
  wire [5:0] waddr, raddr;
  wire [31:0] wdata;
  reg [31:0] rdata;
  axil_regs ctrl (
      .clk(ap_clk), .rst_n(ap_rst_n),
      .awaddr(s_axi_control_AWADDR), .awvalid(s_axi_control_AWVALID), .awready(s_axi_control_AWREADY),
      .wdata(s_axi_control_WDATA), .wstrb(s_axi_control_WSTRB), .wvalid(s_axi_control_WVALID),
      .wready(s_axi_control_WREADY), .bresp(s_axi_control_BRESP), .bvalid(s_axi_control_BVALID),
      .bready(s_axi_control_BREADY), .araddr(s_axi_control_ARADDR), .arvalid(s_axi_control_ARVALID),
      .arready(s_axi_control_ARREADY), .rdata(s_axi_control_RDATA), .rresp(s_axi_control_RRESP),
      .rvalid(s_axi_control_RVALID), .rready(s_axi_control_RREADY),
      .wr(wr), .waddr(waddr), .wdata_o(wdata), .rd(rd), .raddr(raddr), .rdata_i(rdata));
  always @(*) begin
    case (raddr)
      6'h00: rdata = {28'd0, state == IDLE && !start, state == IDLE && !start, done, start};
      6'h10: rdata = dst[31:0];
      6'h14: rdata = dst[63:32];
      6'h1c: rdata = n;
      default: rdata = 32'd0;
    endcase
  end
  assign {m_axi_gmem_ARVALID, m_axi_gmem_ARADDR, m_axi_gmem_ARLEN, m_axi_gmem_ARSIZE, m_axi_gmem_ARBURST} = 0;
  assign m_axi_gmem_RREADY = 1'b0;
  assign m_axi_gmem_AWADDR = dst + {i, 2'b00};
  assign m_axi_gmem_AWLEN = 8'd0;
  assign m_axi_gmem_AWSIZE = 3'd2;
  assign m_axi_gmem_AWBURST = 2'd1;
  assign m_axi_gmem_WDATA = word;
  assign m_axi_gmem_WSTRB = 4'hf;
  assign m_axi_gmem_WLAST = 1'b1;
  assign m_axi_gmem_BREADY = state == RESP;
  assign in_TREADY = state == RECV;
  always @(posedge ap_clk) begin
    if (!ap_rst_n) begin
      state <= IDLE;
      start <= 1'b0;
      done <= 1'b0;
      m_axi_gmem_AWVALID <= 1'b0;
      m_axi_gmem_WVALID <= 1'b0;
    end else begin
      if (wr && waddr == 6'h00 && wdata[0]) start <= 1'b1;
      if (wr && waddr == 6'h10) dst[31:0] <= wdata;
      if (wr && waddr == 6'h14) dst[63:32] <= wdata;
      if (wr && waddr == 6'h1c) n <= wdata;
      if (rd && raddr == 6'h00) done <= 1'b0;
      case (state)
        IDLE:
          if (start) begin
            start <= 1'b0;
            i <= 0;
            if (n == 0) done <= 1'b1;
            else state <= RECV;
          end
        RECV:
          if (in_TVALID) begin
            word <= in_TDATA;
            m_axi_gmem_AWVALID <= 1'b1;
            m_axi_gmem_WVALID <= 1'b1;
            state <= WRITE;
          end
        WRITE: begin
          if (m_axi_gmem_AWREADY) m_axi_gmem_AWVALID <= 1'b0;
          if (m_axi_gmem_WREADY) m_axi_gmem_WVALID <= 1'b0;
          if ((m_axi_gmem_AWREADY || !m_axi_gmem_AWVALID) && (m_axi_gmem_WREADY || !m_axi_gmem_WVALID))
            state <= RESP;
        end
        RESP:
          if (m_axi_gmem_BVALID) begin
            i <= i + 1;
            if (i == n - 1) begin
              done <= 1'b1;
              state <= IDLE;
            end else state <= RECV;
          end
      endcase
    end
  end
endmodule
