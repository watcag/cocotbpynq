`timescale 1ns/1ps
// Video pipeline static region — 6 reconfigurable AXI-Stream stages
// (color → spatial → tone → palette → stylize → finalize) tied to a
// 12-port axis_switch, with each stage owning its own DMA channel.
//
// Each partition exposes a full AXI-Stream slave + master boundary via
// the DPI bridge, so the RM is free to advance state exactly once per
// accepted pixel — no 8-cycle FSM hold like in the auto-generated
// simple-boundary examples. This is what makes the 3x3 line-buffer
// spatials and the per-pixel state machines (pixelate, dither, etc.)
// work correctly.
//
// Switch port layout — for partition index i in [0..5]:
//   SI/MI 2*i + 0  ↔  RM[i]   (RM m_axis → switch SI; switch MI → RM s_axis)
//   SI/MI 2*i + 1  ↔  DMA[i]  (DMA MM2S → switch SI; switch MI → DMA S2MM)
//
// chain([rp_a, rp_b, rp_c]) reprograms the MI muxes to route
//   DMA[a] → RM[a] → RM[b] → RM[c] → DMA[a]
// returning the transformed stream on the first partition's DMA.

module video_pipeline_static (
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

    // DMA0 (rp_color partition)
    input  wire [31:0] x0_tdata, input  wire x0_tvalid, output wire x0_tready, input  wire x0_tlast,
    output wire [31:0] y0_tdata, output wire y0_tvalid, input  wire y0_tready, output wire y0_tlast,
    // DMA1 (rp_spatial)
    input  wire [31:0] x1_tdata, input  wire x1_tvalid, output wire x1_tready, input  wire x1_tlast,
    output wire [31:0] y1_tdata, output wire y1_tvalid, input  wire y1_tready, output wire y1_tlast,
    // DMA2 (rp_tone)
    input  wire [31:0] x2_tdata, input  wire x2_tvalid, output wire x2_tready, input  wire x2_tlast,
    output wire [31:0] y2_tdata, output wire y2_tvalid, input  wire y2_tready, output wire y2_tlast,
    // DMA3 (rp_palette)
    input  wire [31:0] x3_tdata, input  wire x3_tvalid, output wire x3_tready, input  wire x3_tlast,
    output wire [31:0] y3_tdata, output wire y3_tvalid, input  wire y3_tready, output wire y3_tlast,
    // DMA4 (rp_stylize)
    input  wire [31:0] x4_tdata, input  wire x4_tvalid, output wire x4_tready, input  wire x4_tlast,
    output wire [31:0] y4_tdata, output wire y4_tvalid, input  wire y4_tready, output wire y4_tlast,
    // DMA5 (rp_finalize)
    input  wire [31:0] x5_tdata, input  wire x5_tvalid, output wire x5_tready, input  wire x5_tlast,
    output wire [31:0] y5_tdata, output wire y5_tvalid, input  wire y5_tready, output wire y5_tlast
);

    // ── RM AXI-Stream nets (replaced by DPI bridges at build time) ────────
    // For each RM: switch MI[2*i] drives RM s_axis, RM m_axis drives switch SI[2*i].
    wire [31:0] rm0_s_tdata, rm1_s_tdata, rm2_s_tdata, rm3_s_tdata, rm4_s_tdata, rm5_s_tdata;
    wire        rm0_s_tvalid, rm1_s_tvalid, rm2_s_tvalid, rm3_s_tvalid, rm4_s_tvalid, rm5_s_tvalid;
    wire        rm0_s_tready, rm1_s_tready, rm2_s_tready, rm3_s_tready, rm4_s_tready, rm5_s_tready;
    wire        rm0_s_tlast,  rm1_s_tlast,  rm2_s_tlast,  rm3_s_tlast,  rm4_s_tlast,  rm5_s_tlast;

    wire [31:0] rm0_m_tdata, rm1_m_tdata, rm2_m_tdata, rm3_m_tdata, rm4_m_tdata, rm5_m_tdata;
    wire        rm0_m_tvalid, rm1_m_tvalid, rm2_m_tvalid, rm3_m_tvalid, rm4_m_tvalid, rm5_m_tvalid;
    wire        rm0_m_tready, rm1_m_tready, rm2_m_tready, rm3_m_tready, rm4_m_tready, rm5_m_tready;
    wire        rm0_m_tlast,  rm1_m_tlast,  rm2_m_tlast,  rm3_m_tlast,  rm4_m_tlast,  rm5_m_tlast;

    color_rm u_color (
        .clk(clk),
        .s_axis_tdata(rm0_s_tdata), .s_axis_tvalid(rm0_s_tvalid),
        .s_axis_tready(rm0_s_tready), .s_axis_tlast(rm0_s_tlast),
        .m_axis_tdata(rm0_m_tdata), .m_axis_tvalid(rm0_m_tvalid),
        .m_axis_tready(rm0_m_tready), .m_axis_tlast(rm0_m_tlast));

    spatial_rm u_spatial (
        .clk(clk),
        .s_axis_tdata(rm1_s_tdata), .s_axis_tvalid(rm1_s_tvalid),
        .s_axis_tready(rm1_s_tready), .s_axis_tlast(rm1_s_tlast),
        .m_axis_tdata(rm1_m_tdata), .m_axis_tvalid(rm1_m_tvalid),
        .m_axis_tready(rm1_m_tready), .m_axis_tlast(rm1_m_tlast));

    tone_rm u_tone (
        .clk(clk),
        .s_axis_tdata(rm2_s_tdata), .s_axis_tvalid(rm2_s_tvalid),
        .s_axis_tready(rm2_s_tready), .s_axis_tlast(rm2_s_tlast),
        .m_axis_tdata(rm2_m_tdata), .m_axis_tvalid(rm2_m_tvalid),
        .m_axis_tready(rm2_m_tready), .m_axis_tlast(rm2_m_tlast));

    palette_rm u_palette (
        .clk(clk),
        .s_axis_tdata(rm3_s_tdata), .s_axis_tvalid(rm3_s_tvalid),
        .s_axis_tready(rm3_s_tready), .s_axis_tlast(rm3_s_tlast),
        .m_axis_tdata(rm3_m_tdata), .m_axis_tvalid(rm3_m_tvalid),
        .m_axis_tready(rm3_m_tready), .m_axis_tlast(rm3_m_tlast));

    stylize_rm u_stylize (
        .clk(clk),
        .s_axis_tdata(rm4_s_tdata), .s_axis_tvalid(rm4_s_tvalid),
        .s_axis_tready(rm4_s_tready), .s_axis_tlast(rm4_s_tlast),
        .m_axis_tdata(rm4_m_tdata), .m_axis_tvalid(rm4_m_tvalid),
        .m_axis_tready(rm4_m_tready), .m_axis_tlast(rm4_m_tlast));

    finalize_rm u_finalize (
        .clk(clk),
        .s_axis_tdata(rm5_s_tdata), .s_axis_tvalid(rm5_s_tvalid),
        .s_axis_tready(rm5_s_tready), .s_axis_tlast(rm5_s_tlast),
        .m_axis_tdata(rm5_m_tdata), .m_axis_tvalid(rm5_m_tvalid),
        .m_axis_tready(rm5_m_tready), .m_axis_tlast(rm5_m_tlast));

    // ── Switch slave bus (data flowing INTO the switch) ───────────────────
    // 12 ports. Concatenation order: port 11 in the MSBs, port 0 in the LSBs.
    //   SI[2*i]   = RM[i] m_axis (RM output)
    //   SI[2*i+1] = DMA[i] MM2S  (DMA input from PS)
    wire [12*32-1:0] sw_s_tdata = {
        x5_tdata, rm5_m_tdata,
        x4_tdata, rm4_m_tdata,
        x3_tdata, rm3_m_tdata,
        x2_tdata, rm2_m_tdata,
        x1_tdata, rm1_m_tdata,
        x0_tdata, rm0_m_tdata
    };
    wire [11:0] sw_s_tvalid = {
        x5_tvalid, rm5_m_tvalid,
        x4_tvalid, rm4_m_tvalid,
        x3_tvalid, rm3_m_tvalid,
        x2_tvalid, rm2_m_tvalid,
        x1_tvalid, rm1_m_tvalid,
        x0_tvalid, rm0_m_tvalid
    };
    wire [11:0] sw_s_tlast = {
        x5_tlast, rm5_m_tlast,
        x4_tlast, rm4_m_tlast,
        x3_tlast, rm3_m_tlast,
        x2_tlast, rm2_m_tlast,
        x1_tlast, rm1_m_tlast,
        x0_tlast, rm0_m_tlast
    };
    wire [11:0] sw_s_tready;
    assign {x5_tready, rm5_m_tready,
            x4_tready, rm4_m_tready,
            x3_tready, rm3_m_tready,
            x2_tready, rm2_m_tready,
            x1_tready, rm1_m_tready,
            x0_tready, rm0_m_tready} = sw_s_tready;

    // ── Switch master bus (data flowing OUT of the switch) ────────────────
    //   MI[2*i]   = RM[i] s_axis (RM input)
    //   MI[2*i+1] = DMA[i] S2MM  (DMA output to PS)
    wire [12*32-1:0] sw_m_tdata;
    wire [11:0]      sw_m_tvalid;
    wire [11:0]      sw_m_tlast;
    wire [11:0]      sw_m_tready = {
        y5_tready, rm5_s_tready,
        y4_tready, rm4_s_tready,
        y3_tready, rm3_s_tready,
        y2_tready, rm2_s_tready,
        y1_tready, rm1_s_tready,
        y0_tready, rm0_s_tready
    };

    assign {y5_tdata, rm5_s_tdata,
            y4_tdata, rm4_s_tdata,
            y3_tdata, rm3_s_tdata,
            y2_tdata, rm2_s_tdata,
            y1_tdata, rm1_s_tdata,
            y0_tdata, rm0_s_tdata} = sw_m_tdata;
    assign {y5_tvalid, rm5_s_tvalid,
            y4_tvalid, rm4_s_tvalid,
            y3_tvalid, rm3_s_tvalid,
            y2_tvalid, rm2_s_tvalid,
            y1_tvalid, rm1_s_tvalid,
            y0_tvalid, rm0_s_tvalid} = sw_m_tvalid;
    assign {y5_tlast, rm5_s_tlast,
            y4_tlast, rm4_s_tlast,
            y3_tlast, rm3_s_tlast,
            y2_tlast, rm2_s_tlast,
            y1_tlast, rm1_s_tlast,
            y0_tlast, rm0_s_tlast} = sw_m_tlast;

    axis_switch #(.NUM_PORTS(12), .TDATA_WIDTH(32)) u_switch (
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

endmodule
