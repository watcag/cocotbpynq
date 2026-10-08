// Minimal AXI4-Lite slave: one write (AW and W together) or one read at a time.
// wr pulses with waddr/wdata; rd pulses with raddr, and rdata_i (combinational from the kernel) is returned.
module axil_regs #(parameter AW = 6) (
    input  wire          clk,
    input  wire          rst_n,
    input  wire [AW-1:0] awaddr,
    input  wire          awvalid,
    output wire          awready,
    input  wire [31:0]   wdata,
    input  wire [3:0]    wstrb,
    input  wire          wvalid,
    output wire          wready,
    output wire [1:0]    bresp,
    output reg           bvalid,
    input  wire          bready,
    input  wire [AW-1:0] araddr,
    input  wire          arvalid,
    output wire          arready,
    output reg  [31:0]   rdata,
    output wire [1:0]    rresp,
    output reg           rvalid,
    input  wire          rready,
    output wire          wr,
    output wire [AW-1:0] waddr,
    output wire [31:0]   wdata_o,
    output wire          rd,
    output wire [AW-1:0] raddr,
    input  wire [31:0]   rdata_i
);
  assign awready = awvalid && wvalid && !bvalid;
  assign wready = awready;
  assign wr = awready;
  assign waddr = awaddr;
  assign wdata_o = wdata;
  assign bresp = 2'b00;
  assign arready = arvalid && !rvalid;
  assign rd = arready;
  assign raddr = araddr;
  assign rresp = 2'b00;
  always @(posedge clk) begin
    if (!rst_n) begin
      bvalid <= 1'b0;
      rvalid <= 1'b0;
    end else begin
      if (wr) bvalid <= 1'b1;
      else if (bready) bvalid <= 1'b0;
      if (rd) begin
        rvalid <= 1'b1;
        rdata <= rdata_i;
      end else if (rready) rvalid <= 1'b0;
    end
  end
endmodule
