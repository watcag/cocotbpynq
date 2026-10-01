
module poly_sub #(
    parameter integer WIDTH                        = 32,
    parameter integer CONST                        = 1,
    parameter integer C_S_AXI_AXILITES_DATA_WIDTH  = 32,
    parameter integer C_S_AXI_AXILITES_ADDR_WIDTH  = 8,
    parameter integer C_S_AXI_DATA_WIDTH           = 32,
    parameter integer C_S_AXI_AXILITES_WSTRB_WIDTH = (32 / 8),
    parameter integer C_S_AXI_WSTRB_WIDTH          = (32 / 8)
) (
    input  wire                                       clk,
    input  wire                                       rst_n,
    // incoming stream
    input  wire [WIDTH-1:0]                           x_TDATA,
    input  wire                                       x_TVALID,
    output wire                                       x_TREADY,
    input  wire                                       x_TLAST,
    // outgoing stream
    output wire [WIDTH-1:0]                           y_TDATA,
    output wire                                       y_TVALID,
    input  wire                                       y_TREADY,
    output wire                                       y_TLAST,
    // axi lite signals
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

reg y_TVALID_r;
reg y_TLAST_r;
reg [WIDTH-1:0] y_TDATA_r;

always @(posedge clk) begin
    if (~rst_n) begin
        y_TVALID_r <= 1'b0;
        y_TDATA_r  <= 0;
        y_TLAST_r  <= 1'b0;
    end else begin
        y_TVALID_r <= x_TVALID;
        y_TLAST_r  <= x_TLAST;
        if (y_TREADY) begin
            y_TDATA_r <= x_TDATA - CONST;
        end
    end
end

assign x_TREADY = y_TREADY;
assign y_TVALID = y_TVALID_r;
assign y_TDATA  = y_TDATA_r;
assign y_TLAST  = y_TLAST_r;

// AXI-Lite tied off (not used)
assign s_axi_AXILiteS_AWREADY = 1'b1;
assign s_axi_AXILiteS_WREADY  = 1'b1;
assign s_axi_AXILiteS_ARREADY = 1'b1;
assign s_axi_AXILiteS_RVALID  = 1'b0;
assign s_axi_AXILiteS_RDATA   = {C_S_AXI_AXILITES_DATA_WIDTH{1'b0}};
assign s_axi_AXILiteS_RRESP   = 2'b00;
assign s_axi_AXILiteS_BVALID  = 1'b0;
assign s_axi_AXILiteS_BRESP   = 2'b00;

endmodule
