`timescale 1ns/1ps
// Static region for the multi-RP streaming PR example.
//
// Two-stage reconfigurable pipeline:
//   DMA in (x) → stage1_rm → stage2_rm → DMA out (y)
//
// Each stage is an independent reconfigurable partition, swappable at runtime.
// The DPI bridge replaces each module instantiation at build time.

module stream_static (
    input  wire        clk,
    input  wire        rst_n,

    // AXI-Stream subordinate — input from PS (DMA send channel)
    input  wire [31:0] x_tdata,
    input  wire        x_tvalid,
    output wire        x_tready,
    input  wire        x_tlast,

    // AXI-Stream manager — output to PS (DMA recv channel)
    output reg  [31:0] y_tdata,
    output reg         y_tvalid,
    input  wire        y_tready,
    output reg         y_tlast
);

    // ── Stage 1 partition boundary ────────────────────────────────────────
    reg  [31:0] s1_data_in;
    wire [31:0] s1_result;

    stage1_rm u_stage1 (
        .clk     (clk),
        .data_in (s1_data_in),
        .result  (s1_result)
    );

    // ── Stage 2 partition boundary ────────────────────────────────────────
    reg  [31:0] s2_data_in;
    wire [31:0] s2_result;

    stage2_rm u_stage2 (
        .clk     (clk),
        .data_in (s2_data_in),
        .result  (s2_result)
    );

    // ── Stream FSM ───────────────────────────────────────────────────────
    // Process one element at a time through both stages:
    //   IDLE   → accept x word, latch s1_data_in
    //   WAIT1  → 8 cycles for stage1 DPI round-trip
    //   WAIT2  → latch s1_result into s2_data_in, 8 cycles for stage2
    //   OUTPUT → present s2_result on y, wait for y_tready
    localparam S_IDLE = 2'd0, S_WAIT1 = 2'd1, S_WAIT2 = 2'd2, S_OUTPUT = 2'd3;
    reg [1:0] state;
    reg [3:0] wait_cnt;
    reg       last_flag;

    assign x_tready = (state == S_IDLE) & rst_n;

    always @(posedge clk) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            wait_cnt    <= 0;
            y_tvalid    <= 0;
            y_tdata     <= 0;
            y_tlast     <= 0;
            s1_data_in  <= 0;
            s2_data_in  <= 0;
            last_flag   <= 0;
        end else begin
            case (state)
                S_IDLE: begin
                    y_tvalid <= 0;
                    if (x_tvalid & x_tready) begin
                        s1_data_in <= x_tdata;
                        last_flag  <= x_tlast;
                        wait_cnt   <= 0;
                        state      <= S_WAIT1;
                    end
                end

                S_WAIT1: begin
                    wait_cnt <= wait_cnt + 1;
                    if (wait_cnt == 4'd7) begin
                        s2_data_in <= s1_result;
                        wait_cnt   <= 0;
                        state      <= S_WAIT2;
                    end
                end

                S_WAIT2: begin
                    wait_cnt <= wait_cnt + 1;
                    if (wait_cnt == 4'd7) begin
                        y_tdata  <= s2_result;
                        y_tvalid <= 1;
                        y_tlast  <= last_flag;
                        state    <= S_OUTPUT;
                    end
                end

                S_OUTPUT: begin
                    if (y_tready) begin
                        y_tvalid <= 0;
                        state    <= S_IDLE;
                    end
                end
            endcase
        end
    end

endmodule
