`timescale 1ps / 1ps

/*
mem_top - top mem module, instantiates different memories depending on MEM_SIZE
*/

module mem_top
#(
    parameter WIDTH = 32,
    parameter DEPTH = 512,
    parameter PACKS = 1,
    parameter DISTD = 4096,
    parameter URAMD = 32768
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

localparam int MEM_SIZE = WIDTH * DEPTH;

generate
    if (PACKS > 1) begin: packed_mem
        mem_B #(
            .WIDTH ( WIDTH ),
            .DEPTH ( DEPTH ),
            .PACKS ( PACKS )
        )
        mem_inst (
            .rst   ( rst   ),
            .clkA  ( clkA  ),
            .clkB  ( clkB  ),
            .weA   ( weA   ),
            .enA   ( enA   ),
            .enB   ( enB   ),
            .addrA ( addrA ),
            .addrB ( addrB ),
            .dinA  ( dinA  ),
            .doutB ( doutB )
        );
    end else if (MEM_SIZE <= DISTD) begin: distr_mem
        mem_dist #(
            .WIDTH ( WIDTH ),
            .DEPTH ( DEPTH )
        )
        mem_inst (
            .rst   ( rst   ),
            .clkA  ( clkA  ),
            .clkB  ( clkB  ),
            .weA   ( weA   ),
            .enA   ( enA   ),
            .enB   ( enB   ),
            .addrA ( addrA ),
            .addrB ( addrB ),
            .dinA  ( dinA  ),
            .doutB ( doutB )
        );
`ifdef URAMS
    end else if (MEM_SIZE >= URAMD && WIDTH == 32) begin: uram_mem
        uram #(
            .WIDTH ( WIDTH ),
            .DEPTH ( DEPTH )
        )
        mem_inst (
            .rst   ( rst   ),
            .clkA  ( clkA  ),
            .clkB  ( clkB  ),
            .weA   ( weA   ),
            .enA   ( enA   ),
            .enB   ( enB   ),
            .addrA ( addrA ),
            .addrB ( addrB ),
            .dinA  ( dinA  ),
            .doutB ( doutB )
        );
`endif
    end else begin: param_mem
        mem_par #(
            .WIDTH ( WIDTH ),
            .DEPTH ( DEPTH )
        )
        mem_inst (
            .rst   ( rst   ),
            .clkA  ( clkA  ),
            .clkB  ( clkB  ),
            .weA   ( weA   ),
            .enA   ( enA   ),
            .enB   ( enB   ),
            .addrA ( addrA ),
            .addrB ( addrB ),
            .dinA  ( dinA  ),
            .doutB ( doutB )
        );
    end
endgenerate

endmodule
