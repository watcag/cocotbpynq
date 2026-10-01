module median3x3_top #(
    parameter integer WIDTH                        = 32,
    parameter integer C_S_AXI_AXILITES_DATA_WIDTH  = 32,
    parameter integer C_S_AXI_AXILITES_ADDR_WIDTH  = 8,
    parameter integer C_S_AXI_DATA_WIDTH           = 32,
    parameter integer C_S_AXI_AXILITES_WSTRB_WIDTH = (32 / 8),
    parameter integer C_S_AXI_WSTRB_WIDTH          = (32 / 8)
) (
    input  wire                                       clk,
    input  wire                                       rst_n,
    input  wire [WIDTH-1:0]                           x_TDATA,
    input  wire                                       x_TVALID,
    output wire                                       x_TREADY,
    input  wire                                       x_TLAST,
    output wire [WIDTH-1:0]                           y_TDATA,
    output wire                                       y_TVALID,
    input  wire                                       y_TREADY,
    output wire                                       y_TLAST,
    input  wire                                       s_axi_AXILiteS_AWVALID,
    output wire                                       s_axi_AXILiteS_AWREADY,
    input  wire [C_S_AXI_AXILITES_ADDR_WIDTH-1:0]    s_axi_AXILiteS_AWADDR,
    input  wire                                       s_axi_AXILiteS_WVALID,
    output wire                                       s_axi_AXILiteS_WREADY,
    input  wire [C_S_AXI_AXILITES_DATA_WIDTH-1:0]    s_axi_AXILiteS_WDATA,
    input  wire [C_S_AXI_AXILITES_WSTRB_WIDTH-1:0]   s_axi_AXILiteS_WSTRB,
    input  wire                                       s_axi_AXILiteS_ARVALID,
    output wire                                       s_axi_AXILiteS_ARREADY,
    input  wire [C_S_AXI_AXILITES_ADDR_WIDTH-1:0]    s_axi_AXILiteS_ARADDR,
    output wire                                       s_axi_AXILiteS_RVALID,
    input  wire                                       s_axi_AXILiteS_RREADY,
    output wire [C_S_AXI_AXILITES_DATA_WIDTH-1:0]    s_axi_AXILiteS_RDATA,
    output wire [1:0]                                 s_axi_AXILiteS_RRESP,
    output wire                                       s_axi_AXILiteS_BVALID,
    input  wire                                       s_axi_AXILiteS_BREADY,
    output wire [1:0]                                 s_axi_AXILiteS_BRESP
);

wire [3:0] unused_y_TKEEP;
wire [3:0] unused_y_TSTRB;
wire unused_interrupt;

median3x3_hls median3x3_hls_inst (
    .s_axi_AXILiteS_AWVALID(s_axi_AXILiteS_AWVALID),
    .s_axi_AXILiteS_AWREADY(s_axi_AXILiteS_AWREADY),
    .s_axi_AXILiteS_AWADDR(s_axi_AXILiteS_AWADDR[4:0]),
    .s_axi_AXILiteS_WVALID(s_axi_AXILiteS_WVALID),
    .s_axi_AXILiteS_WREADY(s_axi_AXILiteS_WREADY),
    .s_axi_AXILiteS_WDATA(s_axi_AXILiteS_WDATA),
    .s_axi_AXILiteS_WSTRB(s_axi_AXILiteS_WSTRB),
    .s_axi_AXILiteS_ARVALID(s_axi_AXILiteS_ARVALID),
    .s_axi_AXILiteS_ARREADY(s_axi_AXILiteS_ARREADY),
    .s_axi_AXILiteS_ARADDR(s_axi_AXILiteS_ARADDR[4:0]),
    .s_axi_AXILiteS_RVALID(s_axi_AXILiteS_RVALID),
    .s_axi_AXILiteS_RREADY(s_axi_AXILiteS_RREADY),
    .s_axi_AXILiteS_RDATA(s_axi_AXILiteS_RDATA),
    .s_axi_AXILiteS_RRESP(s_axi_AXILiteS_RRESP),
    .s_axi_AXILiteS_BVALID(s_axi_AXILiteS_BVALID),
    .s_axi_AXILiteS_BREADY(s_axi_AXILiteS_BREADY),
    .s_axi_AXILiteS_BRESP(s_axi_AXILiteS_BRESP),
    .ap_clk(clk),
    .ap_rst_n(rst_n),
    .interrupt(unused_interrupt),
    .x_TDATA(x_TDATA),
    .x_TKEEP(4'hF),
    .x_TSTRB(4'hF),
    .x_TLAST(x_TLAST),
    .y_TDATA(y_TDATA),
    .y_TKEEP(unused_y_TKEEP),
    .y_TSTRB(unused_y_TSTRB),
    .y_TLAST(y_TLAST),
    .x_TVALID(x_TVALID),
    .x_TREADY(x_TREADY),
    .y_TVALID(y_TVALID),
    .y_TREADY(y_TREADY)
);

endmodule
