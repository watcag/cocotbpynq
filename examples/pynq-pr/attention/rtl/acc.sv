`timescale 1ps / 1ps

module acc
#(
    parameter D_W     = 32,
    parameter D_W_ACC = 32
)
(
    input wire                      clk,
    input wire                      rst,
    input wire                      enable,
    input wire                      initialize,
    input wire signed [D_W-1:0]     in_data,
    output reg signed [D_W_ACC-1:0] result
);

always @(posedge clk) begin
    if (rst) begin
        result <= 0;
    end else if (enable) begin
        result <= result + in_data;
        if (initialize) begin
            result <= in_data;
        end
    end
end

endmodule
