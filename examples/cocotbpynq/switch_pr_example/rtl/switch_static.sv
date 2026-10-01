`timescale 1ns/1ps
// Static region with AXI-Stream switch for runtime pipeline routing.
//
// 3 partitions (add, sub, mult), each with its own DMA, connected
// through a 6-port axis_switch:
//   SI/MI 0 = RP add (FSM ↔ DPI bridge)
//   SI/MI 1 = DMA add (x0/y0)
//   SI/MI 2 = RP sub
//   SI/MI 3 = DMA sub (x1/y1)
//   SI/MI 4 = RP mult
//   SI/MI 5 = DMA mult (x2/y2)
//
// Default routing: each DMA ↔ its own RM (1:1).
// chain(["add","sub","mult"]): DMA0 → add → sub → mult → DMA0.

module switch_static (
    input  wire        clk,
    input  wire        rst_n,

    // AXI-Lite: switch control
    input  wire [31:0] switch_ctrl_awaddr,
    input  wire        switch_ctrl_awvalid,
    output wire        switch_ctrl_awready,
    input  wire [31:0] switch_ctrl_wdata,
    input  wire [3:0]  switch_ctrl_wstrb,
    input  wire        switch_ctrl_wvalid,
    output wire        switch_ctrl_wready,
    output wire [1:0]  switch_ctrl_bresp,
    output wire        switch_ctrl_bvalid,
    input  wire        switch_ctrl_bready,
    input  wire [31:0] switch_ctrl_araddr,
    input  wire        switch_ctrl_arvalid,
    output wire        switch_ctrl_arready,
    output wire [31:0] switch_ctrl_rdata,
    output wire [1:0]  switch_ctrl_rresp,
    output wire        switch_ctrl_rvalid,
    input  wire        switch_ctrl_rready,

    // DMA0 (add partition)
    input  wire [31:0] x0_tdata,
    input  wire        x0_tvalid,
    output wire        x0_tready,
    input  wire        x0_tlast,
    output wire [31:0] y0_tdata,
    output wire        y0_tvalid,
    input  wire        y0_tready,
    output wire        y0_tlast,

    // DMA1 (sub partition)
    input  wire [31:0] x1_tdata,
    input  wire        x1_tvalid,
    output wire        x1_tready,
    input  wire        x1_tlast,
    output wire [31:0] y1_tdata,
    output wire        y1_tvalid,
    input  wire        y1_tready,
    output wire        y1_tlast,

    // DMA2 (mult partition)
    input  wire [31:0] x2_tdata,
    input  wire        x2_tvalid,
    output wire        x2_tready,
    input  wire        x2_tlast,
    output wire [31:0] y2_tdata,
    output wire        y2_tvalid,
    input  wire        y2_tready,
    output wire        y2_tlast
);

    // ── RM boundaries ─────────────────────────────────────────────────────
    reg  [31:0] add_data_in;  wire [31:0] add_result;
    reg  [31:0] sub_data_in;  wire [31:0] sub_result;
    reg  [31:0] mult_data_in; wire [31:0] mult_result;

    add_rm  u_add  (.clk(clk), .data_in(add_data_in),  .result(add_result));
    sub_rm  u_sub  (.clk(clk), .data_in(sub_data_in),  .result(sub_result));
    mult_rm u_mult (.clk(clk), .data_in(mult_data_in), .result(mult_result));

    // ── Per-partition FSM AXI-Stream wires ────────────────────────────────
    // FSM[i] input (from switch master → partition)
    wire [31:0] fsm0_in_tdata,  fsm1_in_tdata,  fsm2_in_tdata;
    wire        fsm0_in_tvalid, fsm1_in_tvalid, fsm2_in_tvalid;
    wire        fsm0_in_tready, fsm1_in_tready, fsm2_in_tready;
    wire        fsm0_in_tlast,  fsm1_in_tlast,  fsm2_in_tlast;

    // FSM[i] output (from partition → switch slave)
    wire [31:0] fsm0_out_tdata,  fsm1_out_tdata,  fsm2_out_tdata;
    wire        fsm0_out_tvalid, fsm1_out_tvalid, fsm2_out_tvalid;
    wire        fsm0_out_tready, fsm1_out_tready, fsm2_out_tready;
    wire        fsm0_out_tlast,  fsm1_out_tlast,  fsm2_out_tlast;

    // ── Switch slave bus (inputs to switch) ───────────────────────────────
    // Concatenation order: {port5, port4, port3, port2, port1, port0}
    wire [6*32-1:0] sw_s_tdata = {
        x2_tdata,       fsm2_out_tdata,     // SI 5 = DMA2 MM2S, SI 4 = RP mult out
        x1_tdata,       fsm1_out_tdata,     // SI 3 = DMA1 MM2S, SI 2 = RP sub out
        x0_tdata,       fsm0_out_tdata      // SI 1 = DMA0 MM2S, SI 0 = RP add out
    };
    wire [5:0] sw_s_tvalid = {
        x2_tvalid, fsm2_out_tvalid,
        x1_tvalid, fsm1_out_tvalid,
        x0_tvalid, fsm0_out_tvalid
    };
    wire [5:0] sw_s_tlast = {
        x2_tlast, fsm2_out_tlast,
        x1_tlast, fsm1_out_tlast,
        x0_tlast, fsm0_out_tlast
    };
    wire [5:0] sw_s_tready;
    assign {x2_tready, fsm2_out_tready,
            x1_tready, fsm1_out_tready,
            x0_tready, fsm0_out_tready} = sw_s_tready;

    // ── Switch master bus (outputs from switch) ───────────────────────────
    wire [6*32-1:0] sw_m_tdata;
    wire [5:0]      sw_m_tvalid;
    wire [5:0]      sw_m_tlast;

    assign {y2_tdata, fsm2_in_tdata,
            y1_tdata, fsm1_in_tdata,
            y0_tdata, fsm0_in_tdata} = sw_m_tdata;
    assign {y2_tvalid, fsm2_in_tvalid,
            y1_tvalid, fsm1_in_tvalid,
            y0_tvalid, fsm0_in_tvalid} = sw_m_tvalid;
    assign {y2_tlast, fsm2_in_tlast,
            y1_tlast, fsm1_in_tlast,
            y0_tlast, fsm0_in_tlast} = sw_m_tlast;

    wire [5:0] sw_m_tready = {
        y2_tready, fsm2_in_tready,
        y1_tready, fsm1_in_tready,
        y0_tready, fsm0_in_tready
    };

    // ── Switch instance ───────────────────────────────────────────────────
    axis_switch #(.NUM_PORTS(6), .TDATA_WIDTH(32)) u_switch (
        .aclk    (clk),
        .aresetn (rst_n),

        .s_axi_ctrl_awaddr  (switch_ctrl_awaddr[7:0]),
        .s_axi_ctrl_awvalid (switch_ctrl_awvalid),
        .s_axi_ctrl_awready (switch_ctrl_awready),
        .s_axi_ctrl_wdata   (switch_ctrl_wdata),
        .s_axi_ctrl_wstrb   (switch_ctrl_wstrb),
        .s_axi_ctrl_wvalid  (switch_ctrl_wvalid),
        .s_axi_ctrl_wready  (switch_ctrl_wready),
        .s_axi_ctrl_bresp   (switch_ctrl_bresp),
        .s_axi_ctrl_bvalid  (switch_ctrl_bvalid),
        .s_axi_ctrl_bready  (switch_ctrl_bready),
        .s_axi_ctrl_araddr  (switch_ctrl_araddr[7:0]),
        .s_axi_ctrl_arvalid (switch_ctrl_arvalid),
        .s_axi_ctrl_arready (switch_ctrl_arready),
        .s_axi_ctrl_rdata   (switch_ctrl_rdata),
        .s_axi_ctrl_rresp   (switch_ctrl_rresp),
        .s_axi_ctrl_rvalid  (switch_ctrl_rvalid),
        .s_axi_ctrl_rready  (switch_ctrl_rready),

        .s_axis_tdata  (sw_s_tdata),
        .s_axis_tvalid (sw_s_tvalid),
        .s_axis_tready (sw_s_tready),
        .s_axis_tlast  (sw_s_tlast),

        .m_axis_tdata  (sw_m_tdata),
        .m_axis_tvalid (sw_m_tvalid),
        .m_axis_tready (sw_m_tready),
        .m_axis_tlast  (sw_m_tlast)
    );

    // ── FSM: AXI-Stream ↔ simple data_in/result per partition ─────────────
    // Accepts one element from switch, feeds to RM, waits for DPI round-trip,
    // then outputs result back to switch.

    localparam S_IDLE = 2'd0, S_WAIT = 2'd1, S_OUTPUT = 2'd2;

    // ── FSM 0 (add) ──────────────────────────────────────────────────────
    reg [1:0] st0;  reg [3:0] wc0;  reg last0;
    reg [31:0] out0_tdata;  reg out0_tvalid, out0_tlast;

    assign fsm0_in_tready  = (st0 == S_IDLE) & rst_n;
    assign fsm0_out_tdata  = out0_tdata;
    assign fsm0_out_tvalid = out0_tvalid;
    assign fsm0_out_tlast  = out0_tlast;

    always @(posedge clk) begin
        if (!rst_n) begin
            st0 <= S_IDLE; wc0 <= 0; out0_tvalid <= 0;
            out0_tdata <= 0; out0_tlast <= 0;
            add_data_in <= 0; last0 <= 0;
        end else case (st0)
            S_IDLE: begin
                out0_tvalid <= 0;
                if (fsm0_in_tvalid & fsm0_in_tready) begin
                    add_data_in <= fsm0_in_tdata;
                    last0 <= fsm0_in_tlast;
                    wc0 <= 0; st0 <= S_WAIT;
                end
            end
            S_WAIT: begin
                wc0 <= wc0 + 1;
                if (wc0 == 4'd7) begin
                    out0_tdata <= add_result;
                    out0_tvalid <= 1; out0_tlast <= last0;
                    st0 <= S_OUTPUT;
                end
            end
            S_OUTPUT: if (fsm0_out_tready) begin out0_tvalid <= 0; st0 <= S_IDLE; end
            default: st0 <= S_IDLE;
        endcase
    end

    // ── FSM 1 (sub) ──────────────────────────────────────────────────────
    reg [1:0] st1;  reg [3:0] wc1;  reg last1;
    reg [31:0] out1_tdata;  reg out1_tvalid, out1_tlast;

    assign fsm1_in_tready  = (st1 == S_IDLE) & rst_n;
    assign fsm1_out_tdata  = out1_tdata;
    assign fsm1_out_tvalid = out1_tvalid;
    assign fsm1_out_tlast  = out1_tlast;

    always @(posedge clk) begin
        if (!rst_n) begin
            st1 <= S_IDLE; wc1 <= 0; out1_tvalid <= 0;
            out1_tdata <= 0; out1_tlast <= 0;
            sub_data_in <= 0; last1 <= 0;
        end else case (st1)
            S_IDLE: begin
                out1_tvalid <= 0;
                if (fsm1_in_tvalid & fsm1_in_tready) begin
                    sub_data_in <= fsm1_in_tdata;
                    last1 <= fsm1_in_tlast;
                    wc1 <= 0; st1 <= S_WAIT;
                end
            end
            S_WAIT: begin
                wc1 <= wc1 + 1;
                if (wc1 == 4'd7) begin
                    out1_tdata <= sub_result;
                    out1_tvalid <= 1; out1_tlast <= last1;
                    st1 <= S_OUTPUT;
                end
            end
            S_OUTPUT: if (fsm1_out_tready) begin out1_tvalid <= 0; st1 <= S_IDLE; end
            default: st1 <= S_IDLE;
        endcase
    end

    // ── FSM 2 (mult) ─────────────────────────────────────────────────────
    reg [1:0] st2;  reg [3:0] wc2;  reg last2;
    reg [31:0] out2_tdata;  reg out2_tvalid, out2_tlast;

    assign fsm2_in_tready  = (st2 == S_IDLE) & rst_n;
    assign fsm2_out_tdata  = out2_tdata;
    assign fsm2_out_tvalid = out2_tvalid;
    assign fsm2_out_tlast  = out2_tlast;

    always @(posedge clk) begin
        if (!rst_n) begin
            st2 <= S_IDLE; wc2 <= 0; out2_tvalid <= 0;
            out2_tdata <= 0; out2_tlast <= 0;
            mult_data_in <= 0; last2 <= 0;
        end else case (st2)
            S_IDLE: begin
                out2_tvalid <= 0;
                if (fsm2_in_tvalid & fsm2_in_tready) begin
                    mult_data_in <= fsm2_in_tdata;
                    last2 <= fsm2_in_tlast;
                    wc2 <= 0; st2 <= S_WAIT;
                end
            end
            S_WAIT: begin
                wc2 <= wc2 + 1;
                if (wc2 == 4'd7) begin
                    out2_tdata <= mult_result;
                    out2_tvalid <= 1; out2_tlast <= last2;
                    st2 <= S_OUTPUT;
                end
            end
            S_OUTPUT: if (fsm2_out_tready) begin out2_tvalid <= 0; st2 <= S_IDLE; end
            default: st2 <= S_IDLE;
        endcase
    end

endmodule
