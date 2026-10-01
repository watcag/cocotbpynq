`timescale 1ps / 1ps

module counter
#(
    parameter integer MATRIXSIZE_W = 16
)
(
    input wire             clk,
    input wire             rst,
    input wire             enable_pixel_count,
    input wire             enable_slice_count,
    input wire [MATRIXSIZE_W-1:0] WIDTH,
    input wire [MATRIXSIZE_W-1:0] HEIGHT,
    output reg [MATRIXSIZE_W-1:0] pixel_cntr,
    output reg [MATRIXSIZE_W-1:0] slice_cntr
);

always @(posedge clk) begin
    if (rst) begin
        pixel_cntr  <= 0;
    end else begin
        if (enable_pixel_count) begin
            if (pixel_cntr == WIDTH-1) begin
                pixel_cntr <= 0;
            end else begin
                pixel_cntr <= pixel_cntr + 1;
            end
        end
    end
end

always @(posedge clk) begin
    if (rst) begin
        slice_cntr <= 0;
    end else begin
        if (enable_slice_count && pixel_cntr == WIDTH-1) begin
            if (slice_cntr == HEIGHT-1)  begin
                slice_cntr <= 0;
            end else begin
                slice_cntr <= slice_cntr + 1;
            end
        end
    end
end

endmodule
