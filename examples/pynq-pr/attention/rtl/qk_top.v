`timescale 1ps / 1ps

module qk_top #(
    parameter integer D_W                           = 8,
    parameter integer D_W_ACC                       = 32,
    parameter integer SEQ_LEN                       = 32,
    parameter integer HEAD_DIM                      = 64,
    parameter integer N1                            = 4,
    parameter integer N2                            = 4,
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

localparam integer QK_A_WORDS = SEQ_LEN * HEAD_DIM;
localparam integer QK_B_WORDS = HEAD_DIM * SEQ_LEN;

localparam [MATRIXSIZE_W-1:0] QK_BLOCKS               = 1;
localparam [MATRIXSIZE_W-1:0] QK_BLOCK_WIDTH           = SEQ_LEN;
localparam [MATRIXSIZE_W-1:0] QK_BLOCK_WIDTHdN2        = SEQ_LEN / N2;
localparam [MATRIXSIZE_W-1:0] QK_BLOCK_SIZEdN2         = (HEAD_DIM * SEQ_LEN) / N2;
localparam [MATRIXSIZE_W-1:0] QK_M1xBLOCK_WIDTHdN1xN2 = (SEQ_LEN * SEQ_LEN) / (N1 * N2);
localparam [MATRIXSIZE_W-1:0] QK_M1xBLOCK_WIDTHdN1    = (SEQ_LEN * SEQ_LEN) / N1;
localparam [MATRIXSIZE_W-1:0] QK_M2                    = HEAD_DIM;
localparam [MATRIXSIZE_W-1:0] QK_M1xM3dN1              = (SEQ_LEN * SEQ_LEN) / N1;
localparam [MATRIXSIZE_W-1:0] QK_M1dN1                 = SEQ_LEN / N1;
localparam [MATRIXSIZE_W-1:0] QK_M3dN2                 = SEQ_LEN / N2;

localparam [2:0]
    S_IDLE    = 3'd0,
    S_RECV_Q  = 3'd1,
    S_RECV_KT = 3'd2,
    S_QK_A    = 3'd3,
    S_QK_B    = 3'd4,
    S_QK_OUT  = 3'd5;

reg [2:0] state = S_IDLE;
reg [MATRIXSIZE_W-1:0] ptr = 0;

reg signed [D_W-1:0] Q_buf  [0:QK_A_WORDS-1];
reg signed [D_W-1:0] KT_buf [0:QK_B_WORDS-1];

wire                       qk_a_tready;
wire                       qk_b_tready;
wire signed [D_W_ACC-1:0]  qk_out_tdata;
wire                       qk_out_tvalid;
wire                       qk_out_tlast;

/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */

always @(posedge clk) begin
    if (!rst_n) begin
        state <= S_IDLE;
        ptr   <= 0;
    end else begin
        case (state)
            S_IDLE: begin
                ptr   <= 0;
                state <= S_RECV_Q;
            end

            S_RECV_Q: begin
                if (x_TVALID & x_TREADY) begin
                    Q_buf[ptr] <= x_TDATA[D_W-1:0];
                    if (ptr == QK_A_WORDS - 1) begin
                        state <= S_RECV_KT;
                        ptr   <= 0;
                    end else begin
                        ptr <= ptr + 1'b1;
                    end
                end
            end

            S_RECV_KT: begin
                if (x_TVALID & x_TREADY) begin
                    KT_buf[ptr] <= x_TDATA[D_W-1:0];
                    if (ptr == QK_B_WORDS - 1) begin
                        state <= S_QK_A;
                        ptr   <= 0;
                    end else begin
                        ptr <= ptr + 1'b1;
                    end
                end
            end

            S_QK_A: begin
                if (qk_a_tready) begin
                    if (ptr == QK_A_WORDS - 1) begin
                        state <= S_QK_B;
                        ptr   <= 0;
                    end else begin
                        ptr <= ptr + 1'b1;
                    end
                end
            end

            S_QK_B: begin
                if (qk_b_tready) begin
                    if (ptr == QK_B_WORDS - 1) begin
                        state <= S_QK_OUT;
                        ptr   <= 0;
                    end else begin
                        ptr <= ptr + 1'b1;
                    end
                end
            end

            S_QK_OUT: begin
                if (qk_out_tvalid & y_TREADY & qk_out_tlast)
                    state <= S_IDLE;
            end

            default: state <= S_IDLE;
        endcase
    end
end

assign x_TREADY = rst_n & (state == S_RECV_Q | state == S_RECV_KT);
assign y_TDATA  = qk_out_tdata;
assign y_TVALID = (state == S_QK_OUT) & qk_out_tvalid;
assign y_TLAST  = (state == S_QK_OUT) & qk_out_tlast;

mm_pp #(
    .D_W         (D_W),
    .D_W_ACC     (D_W_ACC),
    .N1          (N1),
    .N2          (N2),
    .MATRIXSIZE_W(MATRIXSIZE_W),
    .P_B         (1),
    .KEEP_A      (1),
    .MEM_DEPTH_A (SEQ_LEN * HEAD_DIM),
    .MEM_DEPTH_B (HEAD_DIM * SEQ_LEN),
    .MEM_DEPTH_D (SEQ_LEN * SEQ_LEN),
    .BLOCKED_D   (0),
    .TRANSPOSE_B (0)
) qk_mm (
    .mm_clk               (clk),
    .mm_fclk              (clk),
    .mm_rst_n             (rst_n),
    .s_axis_s2mm_tdata_A  (Q_buf[ptr]),
    .s_axis_s2mm_tlast_A  ((state == S_QK_A) & (ptr == QK_A_WORDS - 1)),
    .s_axis_s2mm_tready_A (qk_a_tready),
    .s_axis_s2mm_tvalid_A (state == S_QK_A),
    .s_axis_s2mm_tdata_B  (KT_buf[ptr]),
    .s_axis_s2mm_tlast_B  ((state == S_QK_B) & (ptr == QK_B_WORDS - 1)),
    .s_axis_s2mm_tready_B (qk_b_tready),
    .s_axis_s2mm_tvalid_B (state == S_QK_B),
    .m_axis_mm2s_tdata    (qk_out_tdata),
    .m_axis_mm2s_tvalid   (qk_out_tvalid),
    .m_axis_mm2s_tready   (state == S_QK_OUT),
    .m_axis_mm2s_tlast    (qk_out_tlast),
    .BLOCKS               (QK_BLOCKS),
    .BLOCK_WIDTH          (QK_BLOCK_WIDTH),
    .BLOCK_WIDTHdN2       (QK_BLOCK_WIDTHdN2),
    .BLOCK_SIZEdN2        (QK_BLOCK_SIZEdN2),
    .M1xBLOCK_WIDTHdN1xN2(QK_M1xBLOCK_WIDTHdN1xN2),
    .M1xBLOCK_WIDTHdN1   (QK_M1xBLOCK_WIDTHdN1),
    .M2                   (QK_M2),
    .M1xM3dN1             (QK_M1xM3dN1),
    .M1dN1                (QK_M1dN1),
    .M3dN2                (QK_M3dN2)
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
