`timescale 1ns/1ps
// Static region with two independently-addressable reconfigurable partitions,
// each with its own DMA AXI-Stream pair.
//
//   DMA0 (x0/y0) ↔ rp0_rm   — partition 0
//   DMA1 (x1/y1) ↔ rp1_rm   — partition 1
//
// Each path has its own FSM; both operate concurrently.

module dual_static (
    input  wire        clk,
    input  wire        rst_n,

    // DMA0: AXI-Stream pair for partition 0
    input  wire [31:0] x0_tdata,
    input  wire        x0_tvalid,
    output wire        x0_tready,
    input  wire        x0_tlast,
    output reg  [31:0] y0_tdata,
    output reg         y0_tvalid,
    input  wire        y0_tready,
    output reg         y0_tlast,

    // DMA1: AXI-Stream pair for partition 1
    input  wire [31:0] x1_tdata,
    input  wire        x1_tvalid,
    output wire        x1_tready,
    input  wire        x1_tlast,
    output reg  [31:0] y1_tdata,
    output reg         y1_tvalid,
    input  wire        y1_tready,
    output reg         y1_tlast
);

    // ── Partition 0 boundary ──────────────────────────────────────────────
    reg  [31:0] rp0_data_in;
    wire [31:0] rp0_result;

    rp0_rm u_rp0 (
        .clk     (clk),
        .data_in (rp0_data_in),
        .result  (rp0_result)
    );

    // ── Partition 1 boundary ──────────────────────────────────────────────
    reg  [31:0] rp1_data_in;
    wire [31:0] rp1_result;

    rp1_rm u_rp1 (
        .clk     (clk),
        .data_in (rp1_data_in),
        .result  (rp1_result)
    );

    // ── FSM for path 0 (DMA0 ↔ RP0) ──────────────────────────────────────
    localparam S_IDLE = 2'd0, S_WAIT = 2'd1, S_OUTPUT = 2'd2;

    reg [1:0] state0;
    reg [3:0] wait0;
    reg       last0;

    assign x0_tready = (state0 == S_IDLE) & rst_n;

    always @(posedge clk) begin
        if (!rst_n) begin
            state0      <= S_IDLE;
            wait0       <= 0;
            y0_tvalid   <= 0;
            y0_tdata    <= 0;
            y0_tlast    <= 0;
            rp0_data_in <= 0;
            last0       <= 0;
        end else begin
            case (state0)
                S_IDLE: begin
                    y0_tvalid <= 0;
                    if (x0_tvalid & x0_tready) begin
                        rp0_data_in <= x0_tdata;
                        last0       <= x0_tlast;
                        wait0       <= 0;
                        state0      <= S_WAIT;
                    end
                end
                S_WAIT: begin
                    wait0 <= wait0 + 1;
                    if (wait0 == 4'd7) begin
                        y0_tdata  <= rp0_result;
                        y0_tvalid <= 1;
                        y0_tlast  <= last0;
                        state0    <= S_OUTPUT;
                    end
                end
                S_OUTPUT: begin
                    if (y0_tready) begin
                        y0_tvalid <= 0;
                        state0    <= S_IDLE;
                    end
                end
                default: state0 <= S_IDLE;
            endcase
        end
    end

    // ── FSM for path 1 (DMA1 ↔ RP1) ──────────────────────────────────────
    reg [1:0] state1;
    reg [3:0] wait1;
    reg       last1;

    assign x1_tready = (state1 == S_IDLE) & rst_n;

    always @(posedge clk) begin
        if (!rst_n) begin
            state1      <= S_IDLE;
            wait1       <= 0;
            y1_tvalid   <= 0;
            y1_tdata    <= 0;
            y1_tlast    <= 0;
            rp1_data_in <= 0;
            last1       <= 0;
        end else begin
            case (state1)
                S_IDLE: begin
                    y1_tvalid <= 0;
                    if (x1_tvalid & x1_tready) begin
                        rp1_data_in <= x1_tdata;
                        last1       <= x1_tlast;
                        wait1       <= 0;
                        state1      <= S_WAIT;
                    end
                end
                S_WAIT: begin
                    wait1 <= wait1 + 1;
                    if (wait1 == 4'd7) begin
                        y1_tdata  <= rp1_result;
                        y1_tvalid <= 1;
                        y1_tlast  <= last1;
                        state1    <= S_OUTPUT;
                    end
                end
                S_OUTPUT: begin
                    if (y1_tready) begin
                        y1_tvalid <= 0;
                        state1    <= S_IDLE;
                    end
                end
                default: state1 <= S_IDLE;
            endcase
        end
    end

endmodule
