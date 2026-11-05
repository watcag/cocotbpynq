proc add_versatile {clk_net versatile_clk_src versatile_freq resetn_net resetn_ext gp0_intf hp1_intf hp1_aclk icap_primitive} {
    # Clocking wizard: raw PS clock -> clk_out1 (versatile), clk_out2 (2x, ICAP)
    set icap_freq [expr {2 * $versatile_freq}]
    set clk_wiz [create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz versatile_clk_wiz]
    set_property -dict [list \
        CONFIG.CLKOUT1_REQUESTED_OUT_FREQ $versatile_freq \
        CONFIG.CLKOUT2_USED {true} \
        CONFIG.CLKOUT2_REQUESTED_OUT_FREQ $icap_freq \
        CONFIG.NUM_OUT_CLKS {2} \
        CONFIG.RESET_PORT {resetn} \
        CONFIG.RESET_TYPE {ACTIVE_LOW} \
        CONFIG.USE_LOCKED {false} \
    ] $clk_wiz

    connect_bd_net $versatile_clk_src [get_bd_pins versatile_clk_wiz/clk_in1]
    connect_bd_net $resetn_ext        [get_bd_pins versatile_clk_wiz/resetn]

    set versatile_clk_net [get_bd_pins versatile_clk_wiz/clk_out1]
    set icap_clk_net      [get_bd_pins versatile_clk_wiz/clk_out2]

    # HP1 clocked from clean clk_wiz output
    connect_bd_net $versatile_clk_net $hp1_aclk

    # Reset systems for versatile and ICAP clock domains
    set versatile_rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset versatile_rst_system]
    set icap_rst      [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset icap_rst_system]

    connect_bd_net $versatile_clk_net [get_bd_pins versatile_rst_system/slowest_sync_clk]
    connect_bd_net $icap_clk_net      [get_bd_pins icap_rst_system/slowest_sync_clk]
    connect_bd_net $resetn_ext        [get_bd_pins versatile_rst_system/ext_reset_in]
    connect_bd_net $resetn_ext        [get_bd_pins icap_rst_system/ext_reset_in]

    # AXI interconnect for CDC between GP0 (clk_net domain) and Versatile (versatile_clk_net domain)
    set versatile_axi_periph [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect versatile_axi_periph]
    set_property CONFIG.NUM_MI {1} $versatile_axi_periph

    connect_bd_intf_net $gp0_intf [get_bd_intf_pins versatile_axi_periph/S00_AXI]
    connect_bd_net $clk_net    [get_bd_pins versatile_axi_periph/ACLK]
    connect_bd_net $clk_net    [get_bd_pins versatile_axi_periph/S00_ACLK]
    connect_bd_net $resetn_net [get_bd_pins versatile_axi_periph/ARESETN]
    connect_bd_net $resetn_net [get_bd_pins versatile_axi_periph/S00_ARESETN]
    connect_bd_net $versatile_clk_net [get_bd_pins versatile_axi_periph/M00_ACLK]
    connect_bd_net [get_bd_pins versatile_rst_system/peripheral_aresetn] [get_bd_pins versatile_axi_periph/M00_ARESETN]

    # Versatile hierarchy
    set oldCurInst [current_bd_instance .]
    set hier [create_bd_cell -type hier versatile]
    current_bd_instance $hier

    create_bd_intf_pin -mode Slave  -vlnv xilinx.com:interface:aximm_rtl:1.0 S00_AXI
    create_bd_intf_pin -mode Master -vlnv xilinx.com:interface:aximm_rtl:1.0 interface_aximm
    create_bd_pin -dir I clk
    create_bd_pin -dir I icap_clk
    create_bd_pin -dir I -type rst rstn
    create_bd_pin -dir I -type rst icap_rstn

    # Bitstream_Reader, CDC_BRIDGE, ICAPE wrapper
    create_bd_cell -type module -reference Bitstream_Reader Bitstream_Reader_0
    create_bd_cell -type module -reference CDC_BRIDGE CDC_BRIDGE_0

    set icape_ref ${icap_primitive}_WRAPPER
    set icape_name ${icape_ref}_0
    create_bd_cell -type module -reference $icape_ref $icape_name

    # axi3_ctrl IP
    create_bd_cell -type ip -vlnv user.org:user:axi3_ctrl axi3_ctrl_0

    # AND gate: icap_csib & Bitstream_Reader ready -> axi3_ctrl ready
    set logic [create_bd_cell -type ip -vlnv xilinx.com:ip:util_vector_logic util_vector_logic_0]
    set_property CONFIG.C_SIZE {1} $logic

    # Constant 0: ties ICAP_RDWRB (write mode), hp_ar_fifocount, icap_error
    set const [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant xlconstant_0]
    set_property CONFIG.CONST_VAL {0} $const

    # Interface connections
    connect_bd_intf_net [get_bd_intf_pins S00_AXI]          [get_bd_intf_pins axi3_ctrl_0/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins interface_aximm]   [get_bd_intf_pins Bitstream_Reader_0/interface_aximm]

    # Bitstream_Reader <-> CDC_BRIDGE
    connect_bd_net [get_bd_pins Bitstream_Reader_0/icap_data]       [get_bd_pins CDC_BRIDGE_0/axi3_data]
    connect_bd_net [get_bd_pins Bitstream_Reader_0/icap_data_valid] [get_bd_pins CDC_BRIDGE_0/axi3_data_valid]

    # CDC_BRIDGE <-> ICAPE wrapper
    connect_bd_net [get_bd_pins CDC_BRIDGE_0/icap_data] [get_bd_pins ${icape_name}/ICAP_DATA]
    connect_bd_net [get_bd_pins CDC_BRIDGE_0/icap_csib] [get_bd_pins ${icape_name}/ICAP_CSIB]

    # AND gate: csib & reader_ready -> ctrl ready
    connect_bd_net [get_bd_pins CDC_BRIDGE_0/icap_csib]      [get_bd_pins util_vector_logic_0/Op1]
    connect_bd_net [get_bd_pins Bitstream_Reader_0/ready]     [get_bd_pins util_vector_logic_0/Op2]
    connect_bd_net [get_bd_pins util_vector_logic_0/Res]      [get_bd_pins axi3_ctrl_0/ready]

    # axi3_ctrl -> Bitstream_Reader control signals
    connect_bd_net [get_bd_pins axi3_ctrl_0/first_addr] [get_bd_pins Bitstream_Reader_0/first_addr]
    connect_bd_net [get_bd_pins axi3_ctrl_0/last_addr]  [get_bd_pins Bitstream_Reader_0/last_addr]
    connect_bd_net [get_bd_pins axi3_ctrl_0/last_arlen] [get_bd_pins Bitstream_Reader_0/final_burst]
    connect_bd_net [get_bd_pins axi3_ctrl_0/prg]        [get_bd_pins Bitstream_Reader_0/prg]
    connect_bd_net [get_bd_pins axi3_ctrl_0/start]      [get_bd_pins Bitstream_Reader_0/start]

    # Constant 0 ties
    connect_bd_net [get_bd_pins xlconstant_0/dout] [get_bd_pins Bitstream_Reader_0/hp_ar_fifocount]
    connect_bd_net [get_bd_pins xlconstant_0/dout] [get_bd_pins Bitstream_Reader_0/icap_error]
    connect_bd_net [get_bd_pins xlconstant_0/dout] [get_bd_pins ${icape_name}/ICAP_RDWRB]

    # Clock connections
    connect_bd_net [get_bd_pins icap_clk] [get_bd_pins CDC_BRIDGE_0/clk_dest] [get_bd_pins ${icape_name}/clk]
    connect_bd_net [get_bd_pins clk]      [get_bd_pins Bitstream_Reader_0/clk] [get_bd_pins CDC_BRIDGE_0/clk_src] [get_bd_pins axi3_ctrl_0/s00_axi_aclk]

    # Reset connections
    connect_bd_net [get_bd_pins rstn]      [get_bd_pins Bitstream_Reader_0/rstn] [get_bd_pins axi3_ctrl_0/s00_axi_aresetn]
    connect_bd_net [get_bd_pins icap_rstn] [get_bd_pins CDC_BRIDGE_0/rstn] [get_bd_pins ${icape_name}/rstn]

    current_bd_instance $oldCurInst

    # Connect hierarchy to top-level
    connect_bd_intf_net [get_bd_intf_pins versatile_axi_periph/M00_AXI] [get_bd_intf_pins versatile/S00_AXI]

    # Smartconnect bridges AXI3 (Bitstream_Reader) to HP1 (AXI4 on UltraScale+, AXI3 on Zynq-7000)
    set versatile_sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect versatile_smartconnect]
    set_property CONFIG.NUM_SI {1} $versatile_sc
    connect_bd_intf_net [get_bd_intf_pins versatile/interface_aximm]      [get_bd_intf_pins versatile_smartconnect/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins versatile_smartconnect/M00_AXI] $hp1_intf
    connect_bd_net $versatile_clk_net [get_bd_pins versatile_smartconnect/aclk]
    connect_bd_net [get_bd_pins versatile_rst_system/peripheral_aresetn] [get_bd_pins versatile_smartconnect/aresetn]

    connect_bd_net $versatile_clk_net [get_bd_pins versatile/clk]
    connect_bd_net $icap_clk_net      [get_bd_pins versatile/icap_clk]
    connect_bd_net [get_bd_pins versatile_rst_system/peripheral_aresetn] [get_bd_pins versatile/rstn]
    connect_bd_net [get_bd_pins icap_rst_system/peripheral_aresetn]      [get_bd_pins versatile/icap_rstn]
}

# AXI crossbar with nsi slave and nmi master ports, all on one clock and reset. Zynq keeps the
# axi_interconnect its published results were measured with; Versal has no axi_interconnect, so it
# gets a smartconnect.
proc axi_crossbar {name nsi nmi clk resetn} {
    global family
    if {$family eq "versal"} {
        set cell [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect $name]
        set_property -dict [list CONFIG.NUM_SI $nsi CONFIG.NUM_MI $nmi] $cell
        connect_bd_net $clk    [get_bd_pins $name/aclk]
        connect_bd_net $resetn [get_bd_pins $name/aresetn]
        return $cell
    }
    set cell [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect $name]
    set_property -dict [list CONFIG.NUM_SI $nsi CONFIG.NUM_MI $nmi] $cell
    connect_bd_net $clk    [get_bd_pins $name/ACLK]
    connect_bd_net $resetn [get_bd_pins $name/ARESETN]
    foreach {prefix n} [list S $nsi M $nmi] {
        for {set i 0} {$i < $n} {incr i} {
            connect_bd_net $clk    [get_bd_pins $name/${prefix}[format %02d $i]_ACLK]
            connect_bd_net $resetn [get_bd_pins $name/${prefix}[format %02d $i]_ARESETN]
        }
    }
    return $cell
}

# NoC interconnect (noc_interconnect: true, Versal): the stream NoC replaces the AXI4-Stream switch.
# Endpoints keep the switch's numbering: 2i is partition i, 2i+1 is DMA i. Every source enters the
# NoC at a static NMU, tagged with its destination by the rps_route GPIO (one field per source),
# and TDEST selects the destination. DMA inputs are static NSUs; partition inputs are NSUs inside
# the partitions (utils::add_noc_input), reached over INI paths owned by the static rps_noc
# (DRC BD 41-2478). The GPIO's reset value routes each partition to and from its own DMA.
proc add_noc_interconnect {names clk resetn ctrl_slot} {
    set n [llength $names]
    set n_end [expr {2 * $n}]
    set w 1
    while {(1 << $w) < $n_end} { incr w }
    set c [utils::noc_stream_qos]

    set to_dma {}
    set to_rp {}
    set default 0
    for {set i 0} {$i < $n} {incr i} {
        lappend to_rp  [format "0x%x 0x%x" [expr {2 * $i}] [expr {2 * $i}]]
        lappend to_dma [format "0x%x 0x%x" [expr {2 * $i + 1}] [expr {2 * $i + 1}]]
        set default [expr {$default | ((2 * $i + 1) << (2 * $i * $w)) | ((2 * $i) << ((2 * $i + 1) * $w))}]
    }
    set noc [create_bd_cell -type ip -vlnv xilinx.com:ip:axis_noc rps_noc]
    set_property -dict [list CONFIG.NUM_SI $n_end CONFIG.NUM_MI $n CONFIG.NUM_NSI 0 CONFIG.NUM_NMI $n \
        CONFIG.NUM_CLKS 1 CONFIG.TDEST_WIDTH $w CONFIG.SI_DESTID_PINS [join [lrepeat $n_end 1] ,] \
        CONFIG.MI_TDEST_VALS [join $to_dma ,] CONFIG.NMI_TDEST_VALS [join $to_rp ,]] $noc
    connect_bd_net $clk [get_bd_pins rps_noc/aclk0]

    set route [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio rps_route]
    set_property -dict [list CONFIG.C_ALL_OUTPUTS {1} CONFIG.C_GPIO_WIDTH [expr {$w * $n_end}] \
        CONFIG.C_DOUT_DEFAULT [format 0x%08X $default]] $route
    connect_bd_net $clk    [get_bd_pins rps_route/s_axi_aclk]
    connect_bd_net $resetn [get_bd_pins rps_route/s_axi_aresetn]
    connect_bd_intf_net [get_bd_intf_pins rps_axi_periph/M[format %02d $ctrl_slot]_AXI] [get_bd_intf_pins rps_route/S_AXI]

    for {set s 0} {$s < $n_end} {incr s} {
        set i [expr {$s / 2}]
        set name [lindex $names $i]
        set from [expr {$s % 2 ? "$name/M_AXIS_MM2S" : "$name/s_mm_maxis"}]
        set tx [create_bd_cell -type module -reference noc_stream_tx noc_tx$s]
        set_property CONFIG.DEST_W $w $tx
        set dest [create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice noc_dest$s]
        set_property -dict [list CONFIG.DIN_WIDTH [expr {$w * $n_end}] \
            CONFIG.DIN_FROM [expr {$w * $s + $w - 1}] CONFIG.DIN_TO [expr {$w * $s}]] $dest
        connect_bd_net [get_bd_pins rps_route/gpio_io_o] [get_bd_pins noc_dest$s/Din]
        connect_bd_net [get_bd_pins noc_dest$s/Dout] [get_bd_pins noc_tx$s/dest]
        connect_bd_intf_net [get_bd_intf_pins $from] [get_bd_intf_pins noc_tx$s/s_axis]
        connect_bd_intf_net [get_bd_intf_pins noc_tx$s/m_axis] [get_bd_intf_pins rps_noc/[format S%02d_AXIS $s]]
        connect_bd_net $clk [get_bd_pins noc_tx$s/clk]
        connect_bd_net $resetn [get_bd_pins noc_tx$s/resetn]
        # A partition sends to any other partition or any DMA; a DMA to any partition.
        set conns {}
        for {set j 0} {$j < $n} {incr j} {
            if {$s % 2 == 1 || $j != $i} { lappend conns [format M%02d_INIS $j] $c }
            if {$s % 2 == 0}             { lappend conns [format M%02d_AXIS $j] $c }
        }
        set_property CONFIG.CONNECTIONS $conns [get_bd_intf_pins rps_noc/[format S%02d_AXIS $s]]
    }
    for {set i 0} {$i < $n} {incr i} {
        set name [lindex $names $i]
        set ini [get_bd_intf_pins rps_noc/[format M%02d_INIS $i]]
        set_property CONFIG.INI_STRATEGY load $ini
        connect_bd_intf_net $ini [get_bd_intf_pins $name/S_INIS]
        create_bd_cell -type module -reference noc_stream_narrow noc_narrow$i
        connect_bd_intf_net [get_bd_intf_pins rps_noc/[format M%02d_AXIS $i]] [get_bd_intf_pins noc_narrow$i/s_axis]
        connect_bd_intf_net [get_bd_intf_pins noc_narrow$i/m_axis] [get_bd_intf_pins $name/S_AXIS_S2MM]
        connect_bd_net $clk [get_bd_pins noc_narrow$i/clk]
    }
}

set design_name $project_name
create_bd_design $design_name

source [file join $script_dir ps_${board_name}.tcl]

set num_rps [llength $partition_names]

set gpio_decouple [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio gpio_decouple]
set_property CONFIG.C_ALL_OUTPUTS {1} $gpio_decouple
connect_bd_net $clk_net    [get_bd_pins gpio_decouple/s_axi_aclk]
connect_bd_net $resetn_net [get_bd_pins gpio_decouple/s_axi_aresetn]

# RP control path: GP1 -> rps_axi_periph
# 2*N+1 masters: N dma + N decoupler + gpio_decouple (+ 1 for the axis_switch ctrl or the NoC's rps_route)
if {$axis_switch eq "1" || $noc_interconnect eq "1"} {
    set num_mi [expr {2 * $num_rps + 2}]
} else {
    set num_mi [expr {2 * $num_rps + 1}]
}
axi_crossbar rps_axi_periph 1 $num_mi $clk_net $resetn_net
connect_bd_intf_net $gp1_intf [get_bd_intf_pins rps_axi_periph/S00_AXI]

# gpio_decouple connects to master slot 2*N
set mi_gpio [format "%02d" [expr {2 * $num_rps}]]
connect_bd_intf_net [get_bd_intf_pins rps_axi_periph/M${mi_gpio}_AXI] [get_bd_intf_pins gpio_decouple/S_AXI]

# axis_switch for runtime RP-to-RP routing
if {$axis_switch eq "1"} {
    set switch_num_ports [expr {2 * $num_rps}]
    set rps_axis_switch [create_bd_cell -type ip -vlnv xilinx.com:ip:axis_switch rps_axis_switch]
    set_property -dict [list \
        CONFIG.NUM_SI $switch_num_ports \
        CONFIG.NUM_MI $switch_num_ports \
        CONFIG.ROUTING_MODE {1} \
    ] $rps_axis_switch

    connect_bd_net $clk_net    [get_bd_pins rps_axis_switch/aclk]
    connect_bd_net $resetn_net [get_bd_pins rps_axis_switch/aresetn]
    connect_bd_net $clk_net    [get_bd_pins rps_axis_switch/s_axi_ctrl_aclk]
    connect_bd_net $resetn_net [get_bd_pins rps_axis_switch/s_axi_ctrl_aresetn]

    # S_AXI_CTRL connects to master slot 2*N+1
    set mi_switch [format "%02d" [expr {2 * $num_rps + 1}]]
    connect_bd_intf_net [get_bd_intf_pins rps_axi_periph/M${mi_switch}_AXI] [get_bd_intf_pins rps_axis_switch/S_AXI_CTRL]
}

# RP data path: crossbar (2N slaves: N MM2S + N S2MM) -> HP0
axi_crossbar rps_interconnect [expr {2 * $num_rps}] 1 $clk_net $resetn_net
connect_bd_intf_net [get_bd_intf_pins rps_interconnect/M00_AXI] $hp0_intf

# DFX decoupler interface config (same for all RPs and matches dummy.v boundary)
set dfx_all_params {INTF {mm_saxis {ID 0 VLNV xilinx.com:interface:axis_rtl:1.0 MODE slave SIGNALS \
    {TVALID {PRESENT 1 WIDTH 1} TREADY {PRESENT 1 WIDTH 1} TDATA {PRESENT 1 WIDTH 32} TLAST {PRESENT 1 WIDTH 1 DECOUPLED 1} \
    TUSER {PRESENT 0 WIDTH 0} TID {PRESENT 0 WIDTH 0} TDEST {PRESENT 0 WIDTH 0} TSTRB {PRESENT 0 WIDTH 4} TKEEP {PRESENT 1 WIDTH 4}}} \
    mm_maxis {ID 1 VLNV xilinx.com:interface:axis_rtl:1.0 SIGNALS {TVALID {PRESENT 1 WIDTH 1} TREADY {PRESENT 1 WIDTH 1} TDATA \
    {PRESENT 1 WIDTH 32} TLAST {PRESENT 1 WIDTH 1} TUSER {PRESENT 0 WIDTH 0} TID {PRESENT 0 WIDTH 0} TDEST {PRESENT 0 WIDTH 0} \
    TSTRB {PRESENT 0 WIDTH 4} TKEEP {PRESENT 0 WIDTH 4}}} AXILiteS \
    {ID 2 VLNV xilinx.com:interface:aximm_rtl:1.0 MODE slave PROTOCOL AXI4LITE SIGNALS {ARVALID {PRESENT 1 WIDTH 1} ARREADY \
    {PRESENT 1 WIDTH 1} AWVALID {PRESENT 1 WIDTH 1} AWREADY {PRESENT 1 WIDTH 1} BVALID {PRESENT 1 WIDTH 1} BREADY \
    {PRESENT 1 WIDTH 1} RVALID {PRESENT 1 WIDTH 1} RREADY {PRESENT 1 WIDTH 1} WVALID {PRESENT 1 WIDTH 1} WREADY \
    {PRESENT 1 WIDTH 1} AWADDR {PRESENT 1 WIDTH 8} AWLEN {PRESENT 0 WIDTH 8} AWSIZE {PRESENT 0 WIDTH 3} AWBURST \
    {PRESENT 0 WIDTH 2} AWLOCK {PRESENT 0 WIDTH 1} AWCACHE {PRESENT 0 WIDTH 4} AWPROT {PRESENT 0 WIDTH 3} WDATA \
    {PRESENT 1 WIDTH 32} WSTRB {PRESENT 1 WIDTH 4} WLAST {PRESENT 0 WIDTH 1} BRESP {PRESENT 1 WIDTH 2} ARADDR \
    {PRESENT 1 WIDTH 8} ARLEN {PRESENT 0 WIDTH 8} ARSIZE {PRESENT 0 WIDTH 3} ARBURST {PRESENT 0 WIDTH 2} ARLOCK \
    {PRESENT 0 WIDTH 1} ARCACHE {PRESENT 0 WIDTH 4} ARPROT {PRESENT 0 WIDTH 3} RDATA {PRESENT 1 WIDTH 32} RRESP \
    {PRESENT 1 WIDTH 2} RLAST {PRESENT 0 WIDTH 1} AWID {WIDTH 0 PRESENT 0} AWREGION {WIDTH 4 PRESENT 0} AWQOS \
    {WIDTH 4 PRESENT 0} AWUSER {WIDTH 0 PRESENT 0} WID {WIDTH 0 PRESENT 0} WUSER {WIDTH 0 PRESENT 0} BID \
    {WIDTH 0 PRESENT 0} BUSER {WIDTH 0 PRESENT 0} ARID {WIDTH 0 PRESENT 0} ARREGION {WIDTH 4 PRESENT 0} ARQOS \
    {WIDTH 4 PRESENT 0} ARUSER {WIDTH 0 PRESENT 0} RID {WIDTH 0 PRESENT 0} RUSER {WIDTH 0 PRESENT 0}}}} IPI_PROP_COUNT 2}

# With the NoC interconnect a partition's input arrives over the NoC, whose endpoint inside the
# partition the PLM quiesces during reconfiguration, so the decoupler covers only the output stream
# and AXI-Lite; the NoC input is part of the partition ($rm_cells, grouped by create_rp_bdc.tcl).
set dec_params $dfx_all_params
set dec_gui_intf mm_saxis
set rm_cells [list dummy]
if {$noc_interconnect eq "1"} {
    set dec_intf [dict get $dfx_all_params INTF]
    dict unset dec_intf mm_saxis
    dict set dec_intf mm_maxis ID 0
    dict set dec_intf AXILiteS ID 1
    dict set dec_params INTF $dec_intf
    set dec_gui_intf mm_maxis
    set rm_cells [list dummy noc_rx noc_narrow]
}

# Create per-RP hierarchies
for {set i 0} {$i < $num_rps} {incr i} {
    set name    [lindex $partition_names $i]
    set mi_dma  [format "%02d" [expr {2 * $i}]]
    set mi_dec  [format "%02d" [expr {2 * $i + 1}]]
    set si_mm2s [format "%02d" [expr {2 * $i}]]
    set si_s2mm [format "%02d" [expr {2 * $i + 1}]]

    set oldCurInst [current_bd_instance .]
    set hier [create_bd_cell -type hier $name]
    current_bd_instance $hier

    # Hierarchy interface pins
    create_bd_intf_pin -mode Slave  -vlnv xilinx.com:interface:aximm_rtl:1.0 S_AXI_LITE
    create_bd_intf_pin -mode Slave  -vlnv xilinx.com:interface:aximm_rtl:1.0 S_AXI_DEC
    create_bd_intf_pin -mode Master -vlnv xilinx.com:interface:aximm_rtl:1.0 M_AXI_MM2S
    create_bd_intf_pin -mode Master -vlnv xilinx.com:interface:aximm_rtl:1.0 M_AXI_S2MM
    create_bd_pin -dir I -type clk clk
    create_bd_pin -dir I -type rst rst_n
    create_bd_pin -dir I decouple

    if {$axis_switch eq "1" || $noc_interconnect eq "1"} {
        # Expose DMA and decoupler AXI-Stream ports for external switch (or NoC) routing
        create_bd_intf_pin -mode Master -vlnv xilinx.com:interface:axis_rtl:1.0 M_AXIS_MM2S
        create_bd_intf_pin -mode Slave  -vlnv xilinx.com:interface:axis_rtl:1.0 S_AXIS_S2MM
        create_bd_intf_pin -mode Master -vlnv xilinx.com:interface:axis_rtl:1.0 s_mm_maxis
        if {$noc_interconnect eq "1"} {
            create_bd_intf_pin -mode Slave -vlnv xilinx.com:interface:inis_rtl:1.0 S_INIS
        } else {
            create_bd_intf_pin -mode Slave -vlnv xilinx.com:interface:axis_rtl:1.0 s_mm_saxis
        }
    }

    # AXI DMA
    set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma dma]
    set_property -dict [list \
        CONFIG.c_include_sg {0} \
        CONFIG.c_m_axi_mm2s_data_width {64} \
        CONFIG.c_m_axis_mm2s_tdata_width {32} \
        CONFIG.c_s_axis_s2mm_tdata_width {32} \
        CONFIG.c_mm2s_burst_size {16} \
        CONFIG.c_sg_length_width {26} \
    ] $dma

    # DFX Decoupler
    set decoupler [create_bd_cell -type ip -vlnv xilinx.com:ip:dfx_decoupler decoupler]
    set_property -dict [list \
        CONFIG.ALL_PARAMS $dec_params \
        CONFIG.GUI_INTERFACE_NAME $dec_gui_intf \
        CONFIG.GUI_INTERFACE_REGISTER {false} \
    ] $decoupler

    # Dummy placeholder
    set dummy [create_bd_cell -type module -reference dummy dummy]

    # Decoupler <-> Dummy connections (the input comes from the NoC with the NoC interconnect)
    if {$noc_interconnect eq "1"} {
        connect_bd_intf_net [utils::add_noc_input [get_bd_intf_pins S_INIS] [get_bd_pins clk]] [get_bd_intf_pins dummy/x]
    } else {
        connect_bd_intf_net [get_bd_intf_pins decoupler/rp_mm_saxis] [get_bd_intf_pins dummy/x]
    }
    connect_bd_intf_net [get_bd_intf_pins dummy/y]               [get_bd_intf_pins decoupler/rp_mm_maxis]
    connect_bd_intf_net [get_bd_intf_pins decoupler/rp_AXILiteS] [get_bd_intf_pins dummy/s_axi_AXILiteS]

    if {$axis_switch eq "1"} {
        # Expose streams for external switch routing
        connect_bd_intf_net [get_bd_intf_pins dma/M_AXIS_MM2S]     [get_bd_intf_pins M_AXIS_MM2S]
        connect_bd_intf_net [get_bd_intf_pins S_AXIS_S2MM]         [get_bd_intf_pins dma/S_AXIS_S2MM]
        connect_bd_intf_net [get_bd_intf_pins s_mm_saxis]          [get_bd_intf_pins decoupler/s_mm_saxis]
        connect_bd_intf_net [get_bd_intf_pins decoupler/s_mm_maxis] [get_bd_intf_pins s_mm_maxis]
    } elseif {$noc_interconnect eq "1"} {
        # Expose streams for NoC routing (the partition input is S_INIS)
        connect_bd_intf_net [get_bd_intf_pins dma/M_AXIS_MM2S]     [get_bd_intf_pins M_AXIS_MM2S]
        connect_bd_intf_net [get_bd_intf_pins S_AXIS_S2MM]         [get_bd_intf_pins dma/S_AXIS_S2MM]
        connect_bd_intf_net [get_bd_intf_pins decoupler/s_mm_maxis] [get_bd_intf_pins s_mm_maxis]
    } else {
        # Direct DMA <-> Decoupler wiring
        connect_bd_intf_net [get_bd_intf_pins dma/M_AXIS_MM2S]     [get_bd_intf_pins decoupler/s_mm_saxis]
        connect_bd_intf_net [get_bd_intf_pins decoupler/s_mm_maxis] [get_bd_intf_pins dma/S_AXIS_S2MM]
    }

    # Hierarchy pin connections
    connect_bd_intf_net [get_bd_intf_pins S_AXI_LITE]     [get_bd_intf_pins dma/S_AXI_LITE]
    connect_bd_intf_net [get_bd_intf_pins S_AXI_DEC]      [get_bd_intf_pins decoupler/s_AXILiteS]
    connect_bd_intf_net [get_bd_intf_pins dma/M_AXI_MM2S] [get_bd_intf_pins M_AXI_MM2S]
    connect_bd_intf_net [get_bd_intf_pins dma/M_AXI_S2MM] [get_bd_intf_pins M_AXI_S2MM]

    connect_bd_net [get_bd_pins clk]      [get_bd_pins dma/s_axi_lite_aclk]
    connect_bd_net [get_bd_pins clk]      [get_bd_pins dma/m_axi_mm2s_aclk]
    connect_bd_net [get_bd_pins clk]      [get_bd_pins dma/m_axi_s2mm_aclk]
    connect_bd_net [get_bd_pins clk]      [get_bd_pins dummy/clk]
    connect_bd_net [get_bd_pins rst_n]    [get_bd_pins dma/axi_resetn]
    connect_bd_net [get_bd_pins rst_n]    [get_bd_pins dummy/rst_n]
    connect_bd_net [get_bd_pins decouple] [get_bd_pins decoupler/decouple]
    # Versal's decoupler has a clock and reset per interface (none on Zynq)
    foreach pin [get_bd_pins -quiet decoupler/*_aclk] {
        connect_bd_net [get_bd_pins clk] $pin
    }
    foreach pin [get_bd_pins -quiet decoupler/*_arstn] {
        connect_bd_net [get_bd_pins rst_n] $pin
    }

    current_bd_instance $oldCurInst

    # Connect hierarchy to top-level infrastructure
    connect_bd_intf_net [get_bd_intf_pins rps_axi_periph/M${mi_dma}_AXI] [get_bd_intf_pins ${name}/S_AXI_LITE]
    connect_bd_intf_net [get_bd_intf_pins rps_axi_periph/M${mi_dec}_AXI] [get_bd_intf_pins ${name}/S_AXI_DEC]
    connect_bd_intf_net [get_bd_intf_pins ${name}/M_AXI_MM2S] [get_bd_intf_pins rps_interconnect/S${si_mm2s}_AXI]
    connect_bd_intf_net [get_bd_intf_pins ${name}/M_AXI_S2MM] [get_bd_intf_pins rps_interconnect/S${si_s2mm}_AXI]

    connect_bd_net $clk_net    [get_bd_pins ${name}/clk]
    connect_bd_net $resetn_net [get_bd_pins ${name}/rst_n]

    # xlslice: extract bit i from gpio output to drive this RP's decoupler
    set slice [create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice decouple_${name}]
    set_property -dict [list \
        CONFIG.DIN_FROM $i \
        CONFIG.DIN_TO   $i \
    ] $slice
    connect_bd_net [get_bd_pins gpio_decouple/gpio_io_o] [get_bd_pins decouple_${name}/Din]
    connect_bd_net [get_bd_pins decouple_${name}/Dout]   [get_bd_pins ${name}/decouple]

    # Connect RP streams to axis_switch
    if {$axis_switch eq "1"} {
        # Per RP: 2 slave ports (decoupler output + DMA read) and 2 master ports (decoupler input + DMA write)
        set sw_s_maxis [format "%02d" [expr {2 * $i}]]
        set sw_s_mm2s  [format "%02d" [expr {2 * $i + 1}]]
        set sw_m_saxis [format "%02d" [expr {2 * $i}]]
        set sw_m_s2mm  [format "%02d" [expr {2 * $i + 1}]]

        connect_bd_intf_net [get_bd_intf_pins ${name}/s_mm_maxis]  [get_bd_intf_pins rps_axis_switch/S${sw_s_maxis}_AXIS]
        connect_bd_intf_net [get_bd_intf_pins ${name}/M_AXIS_MM2S] [get_bd_intf_pins rps_axis_switch/S${sw_s_mm2s}_AXIS]
        connect_bd_intf_net [get_bd_intf_pins rps_axis_switch/M${sw_m_saxis}_AXIS] [get_bd_intf_pins ${name}/s_mm_saxis]
        connect_bd_intf_net [get_bd_intf_pins rps_axis_switch/M${sw_m_s2mm}_AXIS]  [get_bd_intf_pins ${name}/S_AXIS_S2MM]
    }
}

if {$noc_interconnect eq "1"} {
    add_noc_interconnect $partition_names $clk_net $resetn_net [expr {2 * $num_rps + 1}]
}

if {$reconfiguration_method eq "icap"} {
    add_versatile $clk_net $versatile_clk_src $versatile_freq $resetn_net $resetn_ext $gp0_intf $hp1_intf $hp1_aclk $icap_primitive
} elseif {$hp1_aclk ne ""} {
    # HP1 enabled but unused in PCAP mode — connect clock for validation
    connect_bd_net $versatile_clk_src $hp1_aclk
}

validate_bd_design
save_bd_design
close_bd_design $design_name
