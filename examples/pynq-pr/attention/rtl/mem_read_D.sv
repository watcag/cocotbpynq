`timescale 1ps / 1ps

module mem_read_D
#(
    parameter integer N1           = 4,
    parameter integer N2           = 4,
    parameter integer MATRIXSIZE_W = 16,
    parameter integer ADDR_W       = 12
)
(
    input  wire                    clk,
    input  wire                    rst,
    input  wire [MATRIXSIZE_W-1:0] M3,
    input  wire [MATRIXSIZE_W-1:0] M1dN1,
    input  wire                    valid_D,
    output wire [ADDR_W-1:0]       rd_addr_D,
    output wire [N1-1:0]           activate_D
);

reg [ADDR_W-1:0]       rd_addr_D_r = 0;
reg [N1-1:0]           activate_D_r = 0;
reg [N1-1:0]           activate_D_rr = 1;
reg [MATRIXSIZE_W-1:0] col = 0;
reg [$clog2(N1)-1:0]   sys_row = 0;
reg [MATRIXSIZE_W-1:0] offset = 0;
reg [MATRIXSIZE_W-1:0] phase = 0;
reg [$clog2(N2)-1:0]   mini_col = 0;
reg [MATRIXSIZE_W-1:0] mini_offset = 0;

assign rd_addr_D = rd_addr_D_r;
assign activate_D = activate_D_r;

always @(posedge clk) begin
    if (rst) begin 
        col         <= 0;
        sys_row     <= 0;
        offset      <= 0;
        phase       <= 0;
        mini_col    <= 0;
        mini_offset <= 0;
        rd_addr_D_r <= 0;
    end else if (valid_D) begin
        col <= col + 1;
        mini_col <= mini_col + 1;
        
        if (mini_col == N2-1) begin
            mini_col    <= 0;
            mini_offset <= mini_offset + N2;
        end
        
        if (col == M3-1) begin
            col <= 0;
            mini_offset <= 0;
            sys_row <= sys_row + 1;
            if (sys_row == N1-1) begin
                sys_row <= 0;
                offset  <= offset + M3;
                phase   <= phase + 1;
                if (phase == M1dN1-1) begin
                    offset <= 0;
                    phase  <= 0;
                end
            end
        end

        rd_addr_D_r <= (N2 - mini_col - 1) + mini_offset + offset;
    end
end

integer x;
always @(posedge clk) begin
    if (rst) begin
        activate_D_rr <= 1;      // [0,0,...,1]
        activate_D_r  <= 0;
    end else begin
        activate_D_r <= activate_D_rr;
        if (valid_D) begin
            if (col == M3-1) begin
                activate_D_rr[0] <= (phase == M1dN1-1) ? 0 : activate_D_rr[N1-1];
                for (x = 1; x < N1; x = x + 1) begin
                    activate_D_rr[x] <= activate_D_rr[x-1];
                end
            end
        end
    end
end

endmodule
