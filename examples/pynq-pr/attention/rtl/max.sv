`timescale 1ps / 1ps

module max
#(
    parameter D_W = 32
)
(
    input wire                  clk,
    input wire                  rst,
    input wire                  enable,
    input wire                  initialize,
    input wire signed [D_W-1:0] in_data,
    output reg signed [D_W-1:0] result
);

always @(posedge clk) begin
    if (rst) begin
        result <= 0;
    end else if (enable) begin
        result <= (in_data > result) ? in_data : result;
        if (initialize) begin
            result <= in_data;
        end
    end
end

endmodule
