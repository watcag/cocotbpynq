`timescale 1ps / 1ps

/*
mem_dist - distributed memory module
*/

module mem_dist
#(
    parameter WIDTH = 32,
    parameter DEPTH = 512
)
(
    input wire                     rst,
    input wire                     clkA,
    input wire                     clkB,
    input wire                     weA,
    input wire                     enA,
    input wire                     enB,
    input wire [$clog2(DEPTH)-1:0] addrA,
    input wire [$clog2(DEPTH)-1:0] addrB,
    input wire [WIDTH-1:0]         dinA,
    output reg [WIDTH-1:0]         doutB
);

(* ram_style = "distributed" *) reg [WIDTH-1:0] mem [0:DEPTH-1];

`ifndef SYNTHESIS
integer r;
initial begin
    for (r=0; r<=DEPTH-1; r=r+1) begin
        mem[r] = {WIDTH{1'b0}};
    end
end
`endif

always @(posedge clkA) begin
    if (enA) begin
        if (weA) begin
            mem[addrA] <= dinA;
        end
    end
end

always @(posedge clkB) begin
    if (rst) begin
        doutB <= {WIDTH{1'b0}};
    end else if (enB) begin
        doutB <= mem[addrB];
    end
end

endmodule
