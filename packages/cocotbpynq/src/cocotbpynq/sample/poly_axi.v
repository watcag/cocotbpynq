
`timescale 1ns/1ps
module poly (
        clk,
        rst_n,
	// incoming stream
        x_TDATA,
        x_TVALID,
        x_TREADY,
        x_TLAST,
	// outgoing stream
        y_TDATA,
        y_TVALID,
        y_TREADY,
        y_TLAST,
        s_axi_AXILiteS_AWVALID,
        s_axi_AXILiteS_AWREADY,
        s_axi_AXILiteS_AWADDR,
        s_axi_AXILiteS_WVALID,
        s_axi_AXILiteS_WREADY,
        s_axi_AXILiteS_WDATA,
        s_axi_AXILiteS_WSTRB,
        s_axi_AXILiteS_ARVALID,
        s_axi_AXILiteS_ARREADY,
        s_axi_AXILiteS_ARADDR,
        s_axi_AXILiteS_RVALID,
        s_axi_AXILiteS_RREADY,
        s_axi_AXILiteS_RDATA,
        s_axi_AXILiteS_RRESP,
        s_axi_AXILiteS_BVALID,
        s_axi_AXILiteS_BREADY,
        s_axi_AXILiteS_BRESP
);

parameter    C_S_AXI_AXILITES_DATA_WIDTH = 32;
parameter    C_S_AXI_AXILITES_ADDR_WIDTH = 6;
parameter    C_S_AXI_DATA_WIDTH = 32;

parameter C_S_AXI_AXILITES_WSTRB_WIDTH = (32 / 8);
parameter C_S_AXI_WSTRB_WIDTH = (32 / 8);

input   clk;
input   rst_n;
input  [31:0] x_TDATA;
input   x_TVALID;
output   x_TREADY;
input  [0:0] x_TLAST;
output  [31:0] y_TDATA;
output   y_TVALID;
input   y_TREADY;
output  [0:0] y_TLAST;
input   s_axi_AXILiteS_AWVALID;
output   s_axi_AXILiteS_AWREADY;
input  [C_S_AXI_AXILITES_ADDR_WIDTH - 1:0] s_axi_AXILiteS_AWADDR;
input   s_axi_AXILiteS_WVALID;
output   s_axi_AXILiteS_WREADY;
input  [C_S_AXI_AXILITES_DATA_WIDTH - 1:0] s_axi_AXILiteS_WDATA;
input  [C_S_AXI_AXILITES_WSTRB_WIDTH - 1:0] s_axi_AXILiteS_WSTRB;
input   s_axi_AXILiteS_ARVALID;
output   s_axi_AXILiteS_ARREADY;
input  [C_S_AXI_AXILITES_ADDR_WIDTH - 1:0] s_axi_AXILiteS_ARADDR;
output   s_axi_AXILiteS_RVALID;
input   s_axi_AXILiteS_RREADY;
output  [C_S_AXI_AXILITES_DATA_WIDTH - 1:0] s_axi_AXILiteS_RDATA;
output  [1:0] s_axi_AXILiteS_RRESP;
output   s_axi_AXILiteS_BVALID;
input   s_axi_AXILiteS_BREADY;
output  [1:0] s_axi_AXILiteS_BRESP;

wire [31:0] a_V;
wire [31:0] b_V;
wire [31:0] c_V;

poly_AXILiteS_s_axi #(
    .C_S_AXI_ADDR_WIDTH( C_S_AXI_AXILITES_ADDR_WIDTH ),
    .C_S_AXI_DATA_WIDTH( C_S_AXI_AXILITES_DATA_WIDTH ))
poly_AXILiteS_s_axi_U(
    .AWVALID(s_axi_AXILiteS_AWVALID),
    .AWREADY(s_axi_AXILiteS_AWREADY),
    .AWADDR(s_axi_AXILiteS_AWADDR),
    .WVALID(s_axi_AXILiteS_WVALID),
    .WREADY(s_axi_AXILiteS_WREADY),
    .WDATA(s_axi_AXILiteS_WDATA),
    .WSTRB(s_axi_AXILiteS_WSTRB),
    .ARVALID(s_axi_AXILiteS_ARVALID),
    .ARREADY(s_axi_AXILiteS_ARREADY),
    .ARADDR(s_axi_AXILiteS_ARADDR),
    .RVALID(s_axi_AXILiteS_RVALID),
    .RREADY(s_axi_AXILiteS_RREADY),
    .RDATA(s_axi_AXILiteS_RDATA),
    .RRESP(s_axi_AXILiteS_RRESP),
    .BVALID(s_axi_AXILiteS_BVALID),
    .BREADY(s_axi_AXILiteS_BREADY),
    .BRESP(s_axi_AXILiteS_BRESP),
    .ACLK(clk),
    .ARESET(~rst_n),
    .ACLK_EN(1'b1),
    .a_V(a_V),
    .b_V(b_V),
    .c_V(c_V)
);

//------------------------Parameter----------------------
localparam
    RESET = 2'd0,
    EMPTY = 2'd1,
    FULL = 2'd2;

//------------------------Local signal-------------------
reg     [1:0]                   state;
reg     [1:0]                   state_next;
/* internal registers */
reg x_TREADY_r;
reg y_TVALID_r;
reg y_TLAST_r;
reg [31:0] y_TDATA_r;

//------------------------AXI stream fsm------------------

//state
always @(posedge clk) begin
    if(~rst_n) begin
        state <= RESET;
    end else begin
        state <= state_next;
    end
end

//state_next
always @(*) begin
    case (state)
        EMPTY:
            if(x_TVALID & ~y_TREADY)
                state_next = FULL;
            else
                state_next = EMPTY;
        FULL:
            if(y_TREADY)
                state_next = EMPTY;
            else
                state_next = FULL;
        default:
            state_next = EMPTY;
    endcase
end


//signals
always @(posedge clk) begin
	if(~rst_n) begin
		y_TVALID_r <= 1'b0;
		y_TDATA_r <= 0;
		y_TLAST_r <= 1'b0;
		x_TREADY_r <= 1'b0;
	end else begin
		if((state == EMPTY) & x_TVALID ) begin
			y_TDATA_r <= a_V*x_TDATA*x_TDATA+b_V*x_TDATA+c_V;
		    y_TLAST_r <= x_TLAST;
            y_TVALID_r <= 1'b1;
        end else if ((state == EMPTY) | y_TREADY) begin
            y_TVALID_r <= 1'b0;
        end
	end
end

assign x_TREADY = (state == EMPTY);
assign y_TVALID = y_TVALID_r;
assign y_TDATA = y_TDATA_r;
assign y_TLAST = y_TLAST_r;

endmodule //poly

