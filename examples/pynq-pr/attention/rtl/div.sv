`timescale 1ps / 1ps

module div
#(
    parameter integer D_W = 32
)
(
    input  wire           clk,
    input  wire           rst,
    input  wire           enable,
    input  wire           in_valid,
    input  wire [D_W-1:0] divisor,
    input  wire [D_W-1:0] divident,
    output wire [D_W-1:0] quotient,
    output wire           out_valid
);

reg  [D_W-1:0] divisor_r, divisor_r1;
reg  [D_W-1:0] quotient_r;
reg  [D_W-1:0] remainder_r, remainder_r1;
reg div_done_r;

wire [$clog2(D_W)-1:0] divisor_log2;
wire [$clog2(D_W)-1:0] remainder_log2;
reg  [$clog2(D_W)-1:0] divisor_log2_r;
reg  [$clog2(D_W)-1:0] remainder_log2_r;
wire [$clog2(D_W)-1:0] msb;
wire [D_W-1:0] A;
wire [D_W-1:0] B;

assign quotient  = quotient_r;
assign out_valid = div_done_r;

assign msb = (remainder_log2_r - divisor_log2_r);
assign A   = (divisor_r1 << msb);
assign B   = (divisor_r1 << (msb - 1));

enum {INIT, COMP1, COMP2} state;

always @(posedge clk) begin
    if (rst) begin
        state <= INIT;
    end else if (enable) begin
        case (state)
            INIT: begin
                if (in_valid)
                    state <= COMP1;
                else
                    state <= INIT;
            end
            COMP1: begin
                if (remainder_r < divisor_r)
                    state <= INIT;
                else
                    state <= COMP2;
            end
            COMP2: begin
                if (remainder_r1 < divisor_r1)
                    state <= INIT;
                else
                    state <= COMP1;
            end
        endcase
    end
end

always @(posedge clk) begin
    if (rst) begin
        divisor_r    <= 0;
        divisor_r1   <= 0;
        quotient_r   <= 0;
        remainder_r  <= 0;
        remainder_r1 <= 0;
        div_done_r   <= 0;
    end else if (enable) begin
        divisor_log2_r <= divisor_log2;
        remainder_log2_r <= remainder_log2;
        case (state)
            INIT: begin
                divisor_r   <= divisor;
                remainder_r <= divident;
                quotient_r  <= 0;
                div_done_r  <= 0;
            end
            COMP1: begin
                div_done_r <= (remainder_r < divisor_r);
                remainder_r1 <= remainder_r;
                divisor_r1 <= divisor_r;
            end
            COMP2: begin
                div_done_r <= (remainder_r1 < divisor_r1);
                divisor_r <= divisor_r1;
                if (remainder_r1 < A) begin
                    remainder_r       <= remainder_r1 - B;
                    quotient_r[msb-1] <= 1'b1;
                end else begin
                    remainder_r     <= remainder_r1 - A;
                    quotient_r[msb] <= 1'b1;
                end
            end
        endcase
    end
end

lopd #(.D_W(D_W))
divisor_lopd (
    .in_data  ( divisor_r    ),
    .out_data ( divisor_log2 )
);

lopd #(.D_W(D_W))
remainder_lopd (
    .in_data  ( remainder_r    ),
    .out_data ( remainder_log2 )
);

endmodule
