`timescale 1ps / 1ps

/*
mem_par - parametric mem, instantiates and connects individual BRAMs to create a memory of arbitrary size
*/

module mem_par
#(
    parameter WIDTH = 32,
    parameter DEPTH = 512
)
(
    input  wire                     rst,
    input  wire                     clkA,
    input  wire                     clkB,
    input  wire                     weA,
    input  wire                     enA,
    input  wire                     enB,
    input  wire [$clog2(DEPTH)-1:0] addrA,
    input  wire [$clog2(DEPTH)-1:0] addrB,
    input  wire [WIDTH-1:0]         dinA,
    output wire [WIDTH-1:0]         doutB
);

localparam int MEM_DEPTH  = (WIDTH == 8) ? 2048 : 1024;      // 18Kb = 2Kx8b, 36Kb = 1Kx32b
localparam real MEM_SIZE  = (WIDTH * DEPTH) / 1024.0;        // total Kbits of memory
localparam int N_18K      = int'($ceil(MEM_SIZE / 16.0));    // number of 18Kb BRAMs
localparam int N_36K      = int'($ceil(MEM_SIZE / 32.0));    // number of 36Kb BRAMs
localparam int N_BRAMS    = (WIDTH == 8) ? N_18K : N_36K;
localparam int BRAM_WIDTH = WIDTH;
localparam int BRAM_DEPTH = (DEPTH < MEM_DEPTH) ? DEPTH : MEM_DEPTH;

wire [N_BRAMS-1:0]            bram_weA;
wire [N_BRAMS-1:0]            bram_enA;
wire [N_BRAMS-1:0]            bram_enB;
wire [BRAM_WIDTH-1:0]         bram_dinA  [N_BRAMS-1:0];
wire [BRAM_WIDTH-1:0]         bram_doutB [N_BRAMS-1:0];
wire [$clog2(N_BRAMS):0]      bram_indexA;
wire [$clog2(N_BRAMS):0]      bram_indexB;
reg  [$clog2(N_BRAMS):0]      bram_indexB_r = 0;
wire [$clog2(BRAM_DEPTH)-1:0] bram_addrA [N_BRAMS-1:0];
wire [$clog2(BRAM_DEPTH)-1:0] bram_addrB [N_BRAMS-1:0];

/* verilator lint_off SELRANGE */
/* verilator lint_off WIDTHEXPAND */
assign bram_indexA = (DEPTH <= BRAM_DEPTH) ? 0 : addrA[$clog2(DEPTH)-1:$clog2(BRAM_DEPTH)];
assign bram_indexB = (DEPTH <= BRAM_DEPTH) ? 0 : addrB[$clog2(DEPTH)-1:$clog2(BRAM_DEPTH)];
/* verilator lint_on WIDTHEXPAND */
/* verilator lint_on SELRANGE */

assign doutB = bram_doutB[bram_indexB_r];

always @(posedge clkB) begin
    if (rst) begin
        bram_indexB_r <= 0;
    end else if (enB) begin
        bram_indexB_r <= bram_indexB;
    end
end

genvar x;
for (x = 0; x < N_BRAMS; x = x + 1) begin : brams
    assign bram_weA[x] = weA & (bram_indexA == x);
    assign bram_enA[x] = enA & (bram_indexA == x);
    assign bram_enB[x] = enB & (bram_indexB == x);
    assign bram_addrA[x] = addrA[$clog2(BRAM_DEPTH)-1:0];
    assign bram_addrB[x] = addrB[$clog2(BRAM_DEPTH)-1:0];
    assign bram_dinA[x] = dinA;

    mem #(
        .WIDTH(BRAM_WIDTH),
        .DEPTH(BRAM_DEPTH)
    )
    bram (
        .rst(rst),
        .clkA(clkA),
        .clkB(clkB),
        .weA(bram_weA[x]),
        .enA(bram_enA[x]),
        .enB(bram_enB[x]),
        .addrA(bram_addrA[x]),
        .addrB(bram_addrB[x]),
        .dinA(bram_dinA[x]),
        .doutB(bram_doutB[x])
    );
end

endmodule
