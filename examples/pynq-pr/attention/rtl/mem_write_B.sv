`timescale 1ps / 1ps

module mem_write_B
#(
    parameter integer N2           = 4,
    parameter integer MATRIXSIZE_W = 16,
    parameter integer ADDR_W       = 12,
    parameter integer P_B          = 1
)
(
    input  wire                    clk,
    input  wire                    rst,
    input  wire [MATRIXSIZE_W-1:0] M2,
    input  wire [MATRIXSIZE_W-1:0] M3dN2,
    input  wire                    valid_B,
    output wire [ADDR_W-1:0]       wr_addr_B,
    output wire [N2-1:0]           activate_B
);

reg [$clog2(N2)-1:0]   col = 0;
reg [MATRIXSIZE_W-1:0] row = 0;
reg [MATRIXSIZE_W-1:0] offset = 0;
reg [MATRIXSIZE_W-1:0] phase = 0;
reg [ADDR_W-1:0]       wr_addr_B_r = 0;
reg [N2-1:0]           activate_B_r = 0;
reg [N2-1:0]           activate_B_rr = 1;

assign wr_addr_B = wr_addr_B_r;
assign activate_B = activate_B_r;

always @(posedge clk) begin
    if (rst) begin
        col       <= 0;
        row       <= 0;
        offset    <= 0;
        phase     <= 0;
        wr_addr_B_r <= 0;
    end else if (valid_B) begin
        col <= col + 1;
        if (col == N2-1) begin
            col <= 0;
            offset <= offset + M2;
            phase <= phase + 1;
            if (phase == M3dN2-1) begin
                offset <= 0;
                phase <= 0;
                row <= row + P_B;
                if (row == M2-P_B) begin
                    row <= 0;
                end
            end
        end
        wr_addr_B_r <= row + offset;
    end
end

integer x;
always @(posedge clk) begin
    if (rst) begin
        activate_B_rr <= 1;      // [0,0,...,1]
        activate_B_r  <= 0;
    end else begin
        if (valid_B) begin
            activate_B_r <= activate_B_rr;
            activate_B_rr[0] <= (row == M2-1) && (phase == M3dN2-1) ? 0 : activate_B_rr[N2-1];
            for (x = 1; x < N2; x = x + 1) begin
                activate_B_rr[x] <= activate_B_rr[x-1];
            end
        end
    end
end

endmodule
