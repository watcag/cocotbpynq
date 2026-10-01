`timescale 1ps / 1ps

module sfm_top #(
    parameter integer D_W                           = 8,
    parameter integer D_W_ACC                       = 32,
    parameter integer SEQ_LEN                       = 32,
    parameter integer MATRIXSIZE_W                  = 16,
    parameter integer C_S_AXI_AXILITES_DATA_WIDTH   = 32,
    parameter integer C_S_AXI_AXILITES_ADDR_WIDTH   = 8,
    parameter integer C_S_AXI_DATA_WIDTH            = 32,
    parameter integer C_S_AXI_AXILITES_WSTRB_WIDTH  = (32 / 8),
    parameter integer C_S_AXI_WSTRB_WIDTH           = (32 / 8)
) (
    input  wire                                       clk,
    input  wire                                       rst_n,
    input  wire [D_W_ACC-1:0]                         x_TDATA,
    input  wire                                       x_TVALID,
    output wire                                       x_TREADY,
    input  wire                                       x_TLAST,
    output wire signed [D_W_ACC-1:0]                  y_TDATA,
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

localparam integer SM_WORDS = SEQ_LEN * SEQ_LEN;

localparam integer SM_FP_BITS  = 30;
localparam integer SM_MAX_BITS = 30;
localparam integer SM_OUT_BITS = 6;
localparam signed [D_W_ACC-1:0] SM_QB       =  32'sd1216;
localparam signed [D_W_ACC-1:0] SM_QC       =  32'sd563942;
localparam signed [D_W_ACC-1:0] SM_QLN2     = -32'sd312;
localparam signed [D_W_ACC-1:0] SM_QLN2_INV = -32'sd3441481;
localparam        [D_W_ACC-1:0] SM_SREQ     =  32'd62388177;
localparam signed [D_W_ACC-1:0] NEG_MASK    = -32'sd1048576;

localparam [2:0]
    S_IDLE   = 3'd0,
    S_RECV_S = 3'd1,
    S_SM     = 3'd2,
    S_EMIT_P = 3'd3;

reg [2:0] state = S_IDLE;
reg [MATRIXSIZE_W-1:0] ptr        = 0;
reg [MATRIXSIZE_W-1:0] sm_row     = 0;
reg [MATRIXSIZE_W-1:0] sm_col     = 0;
reg [MATRIXSIZE_W-1:0] sm_out_cnt = 0;
reg                    sm_feeding = 1'b0;

reg signed [D_W_ACC-1:0] S_buf [0:SM_WORDS-1];
reg signed [D_W-1:0]     P_buf [0:SM_WORDS-1];

wire                       sm_out_valid;
wire signed [D_W-1:0]      sm_qout;

/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */

always @(posedge clk) begin
    if (!rst_n) begin
        state      <= S_IDLE;
        ptr        <= 0;
        sm_row     <= 0;
        sm_col     <= 0;
        sm_out_cnt <= 0;
        sm_feeding <= 1'b0;
    end else begin
        case (state)
            S_IDLE: begin
                ptr        <= 0;
                sm_row     <= 0;
                sm_col     <= 0;
                sm_out_cnt <= 0;
                sm_feeding <= 1'b0;
                state      <= S_RECV_S;
            end

            S_RECV_S: begin
                if (x_TVALID & x_TREADY) begin
                    S_buf[ptr] <= $signed(x_TDATA);
                    if (ptr == SM_WORDS - 1) begin
                        state      <= S_SM;
                        sm_row     <= 0;
                        sm_col     <= 0;
                        sm_out_cnt <= 0;
                        sm_feeding <= 1'b1;
                    end else begin
                        ptr <= ptr + 1'b1;
                    end
                end
            end

            S_SM: begin
                if (sm_feeding) begin
                    if (sm_col == SEQ_LEN - 1)
                        sm_feeding <= 1'b0;
                    sm_col <= sm_col + 1'b1;
                end
                if (sm_out_valid) begin
                    P_buf[sm_row * SEQ_LEN + sm_out_cnt] <= sm_qout;
                    if (sm_out_cnt == SEQ_LEN - 1) begin
                        if (sm_row == SEQ_LEN - 1) begin
                            state <= S_EMIT_P;
                            ptr   <= 0;
                        end else begin
                            sm_row     <= sm_row + 1'b1;
                            sm_col     <= 0;
                            sm_out_cnt <= 0;
                            sm_feeding <= 1'b1;
                        end
                    end else begin
                        sm_out_cnt <= sm_out_cnt + 1'b1;
                    end
                end
            end

            S_EMIT_P: begin
                if (y_TREADY) begin
                    if (ptr == SM_WORDS - 1)
                        state <= S_IDLE;
                    else
                        ptr <= ptr + 1'b1;
                end
            end

            default: state <= S_IDLE;
        endcase
    end
end

assign x_TREADY = rst_n & (state == S_RECV_S);
assign y_TDATA  = (state == S_EMIT_P) ? {{(D_W_ACC-D_W){1'b0}}, P_buf[ptr]} : 0;
assign y_TVALID = (state == S_EMIT_P);
assign y_TLAST  = (state == S_EMIT_P) & (ptr == SM_WORDS - 1);

softmax #(
    .D_W      (D_W),
    .D_W_ACC  (D_W_ACC),
    .N        (SEQ_LEN),
    .FP_BITS  (SM_FP_BITS),
    .MAX_BITS (SM_MAX_BITS),
    .OUT_BITS (SM_OUT_BITS)
) sm_inst (
    .clk      (clk),
    .rst      (~rst_n),
    .enable   (1'b1),
    .in_valid ((state == S_SM) & sm_feeding),
    .qin      ((sm_col > sm_row) ? NEG_MASK
                                 : S_buf[sm_row * SEQ_LEN + sm_col]),
    .qb       (SM_QB),
    .qc       (SM_QC),
    .qln2     (SM_QLN2),
    .qln2_inv (SM_QLN2_INV),
    .Sreq     (SM_SREQ),
    .out_valid(sm_out_valid),
    .qout     (sm_qout)
);

/* verilator lint_on WIDTHTRUNC */
/* verilator lint_on WIDTHEXPAND */

wire unused_cfg_inputs;
assign unused_cfg_inputs = &{
    1'b0,
    x_TLAST,
    s_axi_AXILiteS_AWVALID,
    s_axi_AXILiteS_AWADDR,
    s_axi_AXILiteS_WVALID,
    s_axi_AXILiteS_WDATA,
    s_axi_AXILiteS_WSTRB,
    s_axi_AXILiteS_ARVALID,
    s_axi_AXILiteS_ARADDR,
    s_axi_AXILiteS_RREADY,
    s_axi_AXILiteS_BREADY,
    C_S_AXI_DATA_WIDTH[0],
    C_S_AXI_WSTRB_WIDTH[0]
};

assign s_axi_AXILiteS_AWREADY = 1'b1;
assign s_axi_AXILiteS_WREADY  = 1'b1;
assign s_axi_AXILiteS_ARREADY = 1'b1;
assign s_axi_AXILiteS_RVALID  = 1'b0;
assign s_axi_AXILiteS_RDATA   = {C_S_AXI_AXILITES_DATA_WIDTH{unused_cfg_inputs & 1'b0}};
assign s_axi_AXILiteS_RRESP   = 2'b00;
assign s_axi_AXILiteS_BVALID  = 1'b0;
assign s_axi_AXILiteS_BRESP   = 2'b00;

endmodule
