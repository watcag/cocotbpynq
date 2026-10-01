/* verilator lint_off WIDTHEXPAND */
`timescale 1ps / 1ps

module mem_write_A
#(
    parameter integer N1           = 4,
    parameter integer MATRIXSIZE_W = 16,
    parameter integer ADDR_W       = 12
)
(
    input  wire                    clk,
    input  wire                    rst,
    input  wire [MATRIXSIZE_W-1:0] M2,
    input  wire [MATRIXSIZE_W-1:0] M1dN1,
    input  wire                    valid_A,
    output wire [ADDR_W-1:0]       wr_addr_A,
    output wire [N1-1:0]           activate_A
);

reg [MATRIXSIZE_W-1:0] col = 0;
reg [$clog2(N1)-1:0]   sys_row = 0;
reg [MATRIXSIZE_W-1:0] offset = 0;
reg [MATRIXSIZE_W-1:0] phase = 0;
reg [ADDR_W-1:0]       wr_addr_A_r = 0;
reg [N1-1:0]           activate_A_r = 0;
reg [N1-1:0]           activate_A_rr = 1;

assign wr_addr_A = wr_addr_A_r;
assign activate_A = activate_A_r;

always @(posedge clk) begin
    if (rst) begin
        col     <= 0;
        sys_row <= 0;
        offset  <= 0;
        phase   <= 0;
        wr_addr_A_r <= 0;
    end else if (valid_A) begin
        col <= col + 1;
        if (col == M2-1) begin
            col <= 0;
            sys_row <= sys_row + 1;
            if (sys_row == N1-1) begin
                sys_row <= 0;
                offset  <= offset + M2;
                phase   <= phase + 1;
                if (phase == M1dN1-1) begin
                    offset <= 0;
                    phase  <= 0;
                end
            end
        end
        wr_addr_A_r <= col + offset;
    end
end

integer x;
always @(posedge clk) begin
    if (rst) begin
        activate_A_rr <= 1;    // [0,0,...,1]
        activate_A_r  <= 0;
    end else begin
        if (valid_A) begin
            activate_A_r <= activate_A_rr;
            if (col == M2-1) begin
                activate_A_rr[0] <= (phase == M1dN1-1) ? 0 : activate_A_rr[N1-1];
                for (x = 1; x < N1; x = x + 1) begin
                    activate_A_rr[x] <= activate_A_rr[x-1];
                end
            end
        end
    end
end

endmodule
/* verilator lint_on WIDTHEXPAND */
