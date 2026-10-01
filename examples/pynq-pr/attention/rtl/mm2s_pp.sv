/* verilator lint_off WIDTHEXPAND */
`timescale 1ps / 1ps

module mm2s_pp
#(
    parameter integer D_W_ACC      = 32,
    parameter integer N1           = 4,
    parameter integer N2           = 4,
    parameter integer MATRIXSIZE_W = 16,
    parameter integer ADDR_W_D     = 12,
    parameter integer MEM_DEPTH_D  = 4096
)
(
    input  wire                           clk,
    input  wire                           fclk,
    input  wire                           rst,
    output wire signed [D_W_ACC-1:0]      m_axis_mm2s_tdata,
    output reg                            m_axis_mm2s_tlast,
    input  wire                           m_axis_mm2s_tready,
    output wire                           m_axis_mm2s_tvalid,
    
    input  wire        [N1-1:0]           valid_D,
    input  wire signed [D_W_ACC-1:0]      data_D [N1-1:0],

    input  wire        [MATRIXSIZE_W-1:0] BLOCKS,
    input  wire        [MATRIXSIZE_W-1:0] BLOCK_WIDTH,
    input  wire        [MATRIXSIZE_W-1:0] M1xBLOCK_WIDTHdN1,

    input  wire        [MATRIXSIZE_W-1:0] M1dN1,
    input  wire        [MATRIXSIZE_W-1:0] M1xM3dN1,

    output reg                            done_multiply
);

wire done_read;
reg start_read = 0;
reg rd_addr_D_valid = 0;
reg reg_rd_addr_D_valid = 0;
reg rd_data_bram_valid = 0;
reg [1:0] done_read_sync = 0;
reg [1:0] done_multiply_sync = 0;
reg [N1-1:0] last_beat = 0;
reg done_multiply_sync_wait = 0;
wire out_tready;

wire        [ADDR_W_D-1:0] wr_addr_D_bram         [N1-1:0];
wire        [ADDR_W_D-1:0] rd_addr_D;

wire        [N1-1:0]       wr_en_D_bram;
wire signed [D_W_ACC-1:0]  wr_data_D_bram         [N1-1:0];
wire signed [D_W_ACC-1:0]  rd_data_D_bram         [N1-1:0];

reg         [N1-1:0]       reg_banked_valid_D;
reg  signed [D_W_ACC-1:0]  reg_banked_data_D      [N1-1:0];
reg         [ADDR_W_D-1:0] reg_banked_read_addr_D [N1-1:0];
reg         [N1-1:0]       reg_banked_activate_D  [N1-1:0];

wire        [N1-1:0]       activate_D;
reg         [N1-1:0]       activate_D_reg;

reg         [MATRIXSIZE_W-1:0] block_index, block_index_r, block_index_rr;

assign out_tready = m_axis_mm2s_tready | ~m_axis_mm2s_tvalid;

// D management
genvar x;
for (x = 0; x < N1; x = x + 1) begin: ram_D
    mem_top #(
        .WIDTH ( D_W_ACC     ),
        .DEPTH ( MEM_DEPTH_D )
    )
    write_ram_D (
        .rst   ( rst                         ),
        .clkA  ( fclk                        ),
        .clkB  ( clk                         ),
        .weA   ( 1'b1                        ),
        .enA   ( wr_en_D_bram[x]             ),
        .enB   ( reg_banked_activate_D[x][x] & out_tready ),
        .addrA ( wr_addr_D_bram[x]           ),
        .addrB ( reg_banked_read_addr_D[x]   ),
        .dinA  ( wr_data_D_bram[x]           ),
        .doutB ( rd_data_D_bram[x]           )
    );

    always @(posedge clk) begin
        if (out_tready) begin
            activate_D_reg[x] <= reg_banked_activate_D[x][x];
        end
    end

    if (x == N1-1) begin
        always @(posedge clk) begin
            if (out_tready) begin
                reg_banked_data_D[x]      <= rd_data_D_bram[x];
                reg_banked_read_addr_D[x] <= rd_addr_D;
                reg_banked_valid_D[x]     <= rd_data_bram_valid;
                reg_banked_activate_D[x]  <= activate_D;
            end
        end
    end else begin
        always @(posedge clk) begin
            if (out_tready) begin
                reg_banked_data_D[x]      <= (activate_D_reg[x] == 1) ? rd_data_D_bram[x] : reg_banked_data_D[x+1];
                reg_banked_read_addr_D[x] <= reg_banked_read_addr_D[x+1];
                reg_banked_valid_D[x]     <= reg_banked_valid_D[x+1];
                reg_banked_activate_D[x]  <= reg_banked_activate_D[x+1];
            end
        end
    end
end

// AXI Signals management
assign done_read = (rd_addr_D == (M1xM3dN1 - N2 + 1)) & activate_D[N1-1] & (block_index_r == BLOCKS - 1);   // last address for D was produced

always @(posedge fclk) begin
    done_read_sync <= {done_read_sync[0], done_read};
end

always @(posedge fclk) begin
    if (rst) begin
        done_multiply <= 0;
    end else begin
        if (done_read_sync[1]) begin
            // axi finished reading out D
            done_multiply <= 0;
        end else  if (wr_addr_D_bram[N1-1] == M1xM3dN1-1) begin
            // systolic finished writing
            done_multiply <= 1;
        end
    end
end

always @(posedge clk) begin
    done_multiply_sync <= {done_multiply_sync[0], done_multiply};
end

always @(posedge clk) begin
    if (rst) begin
        done_multiply_sync_wait <= 0;
    end else begin
        if (out_tready) begin
            if (done_read) begin
                done_multiply_sync_wait <= 1;
            end else if (~done_multiply_sync[1]) begin
                done_multiply_sync_wait <= 0;
            end
        end
    end
end

always @(posedge clk) begin
    if (rst) begin
        start_read <= 0;
        rd_addr_D_valid <= 0;
        reg_rd_addr_D_valid <= 0;
        rd_data_bram_valid <= 0;
    end else begin
        if (out_tready) begin
            start_read <= done_multiply_sync[1];
            if (done_read || done_multiply_sync_wait) begin
                start_read <= 0;
            end
            rd_addr_D_valid <= start_read;
            reg_rd_addr_D_valid <= rd_addr_D_valid;
            rd_data_bram_valid <= reg_rd_addr_D_valid;
        end
    end
end

always @(posedge clk) begin
    if (rst) begin
        block_index_r <= 0;
        block_index_rr <= 0;
    end else begin
        block_index_r <= block_index;
        block_index_rr <= block_index_r; 
    end
end

always @(posedge clk) begin
    if (rst) begin
        last_beat <= 0;
        m_axis_mm2s_tlast <= 0;
    end else begin
        if (out_tready) begin
            last_beat[N1-1] <= (reg_banked_read_addr_D[N1-1] == (M1xM3dN1 - N2)) & reg_banked_activate_D[N1-1][N1-1] & (block_index_rr == BLOCKS - 1);
            for (int i = 0; i < N1 - 1; i++) begin
                last_beat[i] <= last_beat[i+1];
            end
            m_axis_mm2s_tlast <= last_beat[0];
        end
    end
end

assign m_axis_mm2s_tdata = reg_banked_data_D[0];
assign m_axis_mm2s_tvalid = reg_banked_valid_D[0];

mem_write_D #(
    .D_W          ( D_W_ACC      ),
    .N1           ( N1           ),
    .MATRIXSIZE_W ( MATRIXSIZE_W ),
    .ADDR_W       ( ADDR_W_D     )
)
mem_write_D (
    .clk          ( fclk                ),
    .rst          ( rst                 ),
    .M1xM3dN1     ( M1xM3dN1            ),
    .in_valid     ( valid_D             ),
    .in_data      ( data_D              ),
    .wr_addr_bram ( wr_addr_D_bram      ),
    .wr_data_bram ( wr_data_D_bram      ),
    .wr_en_bram   ( wr_en_D_bram        )
);

mem_read_D_pp #(
    .N1           ( N1           ),
    .N2           ( N2           ),
    .MATRIXSIZE_W ( MATRIXSIZE_W ),
    .ADDR_W       ( ADDR_W_D     )
)
mem_read_D_inst (
    .clk               ( clk                 ),
    .rst               ( rst | ~start_read   ),
    .BLOCKS            ( BLOCKS              ),
    .BLOCK_WIDTH       ( BLOCK_WIDTH         ),
    .M1xBLOCK_WIDTHdN1 ( M1xBLOCK_WIDTHdN1   ),
    .M1dN1             ( M1dN1               ),
    .valid_D           ( out_tready & start_read ),
    .rd_addr_D         ( rd_addr_D           ),
    .block_index       ( block_index         ),
    .activate_D        ( activate_D          )
);

endmodule
/* verilator lint_on WIDTHEXPAND */
