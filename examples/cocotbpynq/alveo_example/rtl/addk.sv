// addk (ap_ctrl_none, registers only): y = x + K on a 32-bit AXI4-Stream, TLAST passed through.
// Registers: 0x10 K (read/write), 0x14 words passed (read only, cleared by writing K).
module addk (
    input  wire        ap_clk,
    input  wire        ap_rst_n,
    input  wire [31:0] x_TDATA,
    input  wire        x_TVALID,
    output wire        x_TREADY,
    input  wire        x_TLAST,
    output wire [31:0] y_TDATA,
    output wire        y_TVALID,
    input  wire        y_TREADY,
    output wire        y_TLAST,
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
  reg [31:0] k, count;
  wire wr, rd;
  wire [5:0] waddr, raddr;
  wire [31:0] wdata;
  axil_regs ctrl (
      .clk(ap_clk), .rst_n(ap_rst_n),
      .awaddr(s_axi_control_AWADDR), .awvalid(s_axi_control_AWVALID), .awready(s_axi_control_AWREADY),
      .wdata(s_axi_control_WDATA), .wstrb(s_axi_control_WSTRB), .wvalid(s_axi_control_WVALID),
      .wready(s_axi_control_WREADY), .bresp(s_axi_control_BRESP), .bvalid(s_axi_control_BVALID),
      .bready(s_axi_control_BREADY), .araddr(s_axi_control_ARADDR), .arvalid(s_axi_control_ARVALID),
      .arready(s_axi_control_ARREADY), .rdata(s_axi_control_RDATA), .rresp(s_axi_control_RRESP),
      .rvalid(s_axi_control_RVALID), .rready(s_axi_control_RREADY),
      .wr(wr), .waddr(waddr), .wdata_o(wdata), .rd(rd), .raddr(raddr),
      .rdata_i(raddr == 6'h10 ? k : raddr == 6'h14 ? count : 32'd0));
  assign y_TDATA = x_TDATA + k;
  assign y_TVALID = x_TVALID;
  assign y_TLAST = x_TLAST;
  assign x_TREADY = y_TREADY;
  always @(posedge ap_clk) begin
    if (!ap_rst_n) begin
      k <= 32'd0;
      count <= 32'd0;
    end else if (wr && waddr == 6'h10) begin
      k <= wdata;
      count <= 32'd0;
    end else if (x_TVALID && y_TREADY) count <= count + 1;
  end
endmodule
