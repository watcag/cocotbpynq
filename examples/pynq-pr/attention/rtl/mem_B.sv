`timescale 1ps / 1ps

/*
mem_B - packed memory module
*/

module mem_B
#(
    parameter WIDTH = 32,
    parameter DEPTH = 512,
    parameter PACKS = 1
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
    input  wire [WIDTH*PACKS-1:0]   dinA,
    output wire [WIDTH-1:0]         doutB
);

wire [$clog2(DEPTH/PACKS)-1:0] mem_addrA;
wire [$clog2(DEPTH/PACKS)-1:0] mem_addrB;
reg [$clog2(PACKS)-1:0] indexB;
reg [WIDTH*PACKS-1:0] mem_doutB;
wire [WIDTH-1:0] unp_doutB [PACKS-1:0];

assign mem_addrA = addrA >> $clog2(PACKS);
assign mem_addrB = addrB >> $clog2(PACKS);

genvar i;
generate
    for (i = 0; i < PACKS; i = i + 1) begin : unpacked
        assign unp_doutB[i] = mem_doutB[(i+1)*WIDTH-1-:WIDTH];
    end
endgenerate

assign doutB = unp_doutB[indexB];

// (* ram_style = "block" *) reg [WIDTH*PACKS-1:0] mem [0:DEPTH/PACKS-1];
// (* ram_style = "ultra" *) reg [WIDTH*PACKS-1:0] mem [0:DEPTH/PACKS-1];
reg [WIDTH*PACKS-1:0] mem [0:DEPTH/PACKS-1];

// always @(posedge clkB) begin
always @(posedge clkA) begin
    if (rst) begin
        indexB <= 0;
    end else if (enB) begin
        indexB <= addrB[$clog2(PACKS)-1:0];
    end
end

`ifndef SYNTHESIS
integer r;
initial begin
    for (r=0; r<=DEPTH/PACKS-1; r=r+1) begin
        mem[r] = {WIDTH{1'b0}};
    end
end
`endif

always @(posedge clkA) begin
    if (enA) begin
        if (weA) begin
            mem[mem_addrA] <= dinA;
        end
    end
end

// always @(posedge clkB) begin
always @(posedge clkA) begin
    if (rst) begin
        mem_doutB <= 0;
    end else if (enB) begin
        mem_doutB <= mem[mem_addrB];
    end
end

endmodule
