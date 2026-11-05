# PS configuration for the Alinx VD100 (Versal AI Edge xcve2302).
#
# Alinx ships no Vivado board files, so this script holds what a board preset would:
#   - cips: the board's processing system. The keys below are those that differ from the CIPS
#     defaults; the effective configuration equals Alinx's factory preset (VD100_2023.2,
#     Demo/course_s2 ps_config.tcl) with the PL interface the board's PYNQ device tree expects:
#     pl0_ref_clk at $data_freq MHz, M_AXI_FPD, one fabric reset, no EMIO peripherals and no
#     PL interrupts.
#   - axi_noc_0: the board's 64-bit DDR4-3200 controller (DDR_LOW0, 2 GB at 0x0), the PS paths to
#     it (FPD CCI, LPD, PMC; initial_boot) and one PL port, S06_AXI, for the partitions' DMAs.
#     The PMC path carries the partial PDIs the PLM loads from DDR.
# Pins: constraints/vd100.xdc.
#
# Exports clk_net, resetn_net, resetn_ext, gp1_intf (M_AXI_FPD, control) and hp0_intf (NoC
# S06_AXI, partition data). Versal has no ICAP, so the ICAP-only exports (versatile_clk_src,
# gp0_intf, hp1_intf, hp1_aclk) are empty.

if { ![info exists data_freq] } { set data_freq 100 }

# IP versions are pinned: the CIPS keys below are versal_cips 3.4's (Vivado 2025.1). On another
# Vivado release the cells below fail to create until the keys are checked against its CIPS.

set pmc {
    DDR_MEMORY_MODE {Connectivity to DDR via NOC}
    PMC_USE_PMC_NOC_AXI0 {1}
    PS_USE_FPD_CCI_NOC {1}
    PS_USE_FPD_CCI_NOC0 {1}
    PS_USE_NOC_LPD_AXI0 {1}
    PS_USE_M_AXI_FPD {1}
    PS_USE_PMCPL_CLK0 {1}
    PS_NUM_FABRIC_RESETS {1}

    PMC_CRP_CFU_REF_CTRL_FREQMHZ {320}
    PMC_CRP_EFUSE_REF_CTRL_FREQMHZ {80.000000}
    PMC_CRP_PPLL_CTRL_FBDIV {72}
    PS_CRF_APLL_CTRL_CLKOUTDIV {4}
    PS_CRF_APLL_CTRL_FBDIV {66}
    PS_CRF_DBG_FPD_CTRL_FREQMHZ {334}
    PS_CRF_FPD_TOP_SWITCH_CTRL_FREQMHZ {550}
    PS_CRL_CPM_TOPSW_REF_CTRL_FREQMHZ {480}
    PS_CRL_CPU_R5_CTRL_FREQMHZ {400}
    PS_CRL_DBG_LPD_CTRL_FREQMHZ {333}
    PS_CRL_DBG_TSTMP_CTRL_FREQMHZ {333}
    PS_CRL_IOU_SWITCH_CTRL_FREQMHZ {250}
    PS_CRL_LPD_TOP_SWITCH_CTRL_FREQMHZ {400}
    PS_CRL_RPLL_CTRL_CLKOUTDIV {4}
    PS_CRL_RPLL_CTRL_FBDIV {105}
    PS_CRL_USB0_BUS_REF_CTRL_FREQMHZ {20}

    PMC_QSPI_PERIPHERAL_ENABLE {1}
    PMC_QSPI_PERIPHERAL_MODE {Dual Parallel}
    PMC_QSPI_PERIPHERAL_DATA_MODE {x4}
    PMC_QSPI_FBCLK {{ENABLE 1}}
    PMC_SD0 {{RESET_ENABLE 1} {RESET_IO {PMC_MIO 49}}}
    PMC_SD0_PERIPHERAL {{CLK_200_SDR_OTAP_DLY 0x2} {CLK_50_DDR_ITAP_DLY 0x1E} {CLK_50_DDR_OTAP_DLY 0x5} {CLK_50_SDR_ITAP_DLY 0x2C} {CLK_50_SDR_OTAP_DLY 0x5} {ENABLE 1} {IO {PMC_MIO 37 .. 49}}}
    PMC_SD0_DATA_TRANSFER_MODE {8Bit}
    PMC_SD0_SLOT_TYPE {eMMC}
    PMC_SD0_SPEED_MODE {high speed}
    PMC_SD1 {{CD_ENABLE 1} {CD_IO {PMC_MIO 28}}}
    PMC_SD1_PERIPHERAL {{CLK_50_SDR_ITAP_DLY 0x2C} {CLK_50_SDR_OTAP_DLY 0x4} {ENABLE 1} {IO {PMC_MIO 26 .. 36}}}
    PMC_I2CPMC_PERIPHERAL {{ENABLE 1} {IO {PMC_MIO 34 .. 35}}}
    PS_ENET0_PERIPHERAL {{ENABLE 1} {IO {PS_MIO 0 .. 11}}}
    PS_ENET0_MDIO {{ENABLE 1} {IO {PMC_MIO 50 .. 51}}}
    PS_UART0_PERIPHERAL {{ENABLE 1} {IO {PS_MIO 16 .. 17}}}
    PS_CAN0_PERIPHERAL {{ENABLE 1} {IO {PS_MIO 22 .. 23}}}
    PS_USB3_PERIPHERAL {{ENABLE 1}}
    PS_TTC0_PERIPHERAL_ENABLE {1}
    PS_TTC1_PERIPHERAL_ENABLE {1}
    PS_TTC2_PERIPHERAL_ENABLE {1}
    PS_TTC3_PERIPHERAL_ENABLE {1}
    PS_GEN_IPI0_ENABLE {1}
    PS_GEN_IPI1_ENABLE {1}
    PS_GEN_IPI2_ENABLE {1}
    PS_GEN_IPI3_ENABLE {1}
    PS_GEN_IPI4_ENABLE {1}
    PS_GEN_IPI5_ENABLE {1}
    PS_GEN_IPI6_ENABLE {1}
    PS_ENET1_PERIPHERAL {{IO EMIO}}
    PS_ENET1_MDIO {{IO EMIO}}
    PS_I2C0_PERIPHERAL {{IO EMIO}}
    PS_I2C1_PERIPHERAL {{IO EMIO}}

    PMC_MIO0 {{DIRECTION out} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO1 {{DIRECTION inout} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO2 {{DIRECTION inout} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO3 {{DIRECTION inout} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO4 {{DIRECTION inout} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO5 {{DIRECTION out} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO6 {{DIRECTION out} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO7 {{DIRECTION out} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO8 {{DIRECTION inout} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO9 {{DIRECTION inout} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO10 {{DIRECTION inout} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO11 {{DIRECTION inout} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO12 {{DIRECTION out} {DRIVE_STRENGTH 12mA} {SCHMITT 1} {SLEW fast} {USAGE Reserved}}
    PMC_MIO13 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PMC_MIO24 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PMC_MIO49 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PMC_MIO50 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PS_MIO0 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PS_MIO1 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PS_MIO2 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PS_MIO3 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PS_MIO4 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PS_MIO5 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PS_MIO17 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PS_MIO23 {{DIRECTION out} {SCHMITT 1} {USAGE Reserved}}
    PS_MIO24 {{AUX_IO 0} {DIRECTION in} {DRIVE_STRENGTH 8mA} {OUTPUT_DATA default} {PULL pullup} {SCHMITT 0} {SLEW slow} {USAGE GPIO}}
    PS_MIO25 {{AUX_IO 0} {DIRECTION out} {DRIVE_STRENGTH 8mA} {OUTPUT_DATA default} {PULL pullup} {SCHMITT 0} {SLEW slow} {USAGE GPIO}}
}
dict set pmc PMC_CRP_PL0_REF_CTRL_FREQMHZ $data_freq

set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:versal_cips:3.4 ps]
set_property -dict [list CONFIG.DDR_MEMORY_MODE {Enable} CONFIG.PS_PMC_CONFIG $pmc] $ps

# NoC: DDR4 controller, PS paths and the PL data port.
set noc [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_noc:1.1 axi_noc_0]
set_property -dict [list \
    CONFIG.NUM_SI {7} CONFIG.NUM_MI {0} CONFIG.NUM_CLKS {7} CONFIG.NUM_MC {1} CONFIG.NUM_MCP {4} \
    CONFIG.CONTROLLERTYPE {DDR4_SDRAM} CONFIG.MC_CHAN_REGION1 {NONE} CONFIG.MC_INPUTCLK0_PERIOD {5000} \
    CONFIG.MC_MEMORY_SPEEDGRADE {DDR4-3200AA(22-22-22)} CONFIG.MC_COMPONENT_WIDTH {x16} \
    CONFIG.MC_CASLATENCY {22} CONFIG.MC_USER_DEFINED_ADDRESS_MAP {16RA-2BA-1BG-10CA} \
    CONFIG.MC_ECC_SCRUB_SIZE {4096} CONFIG.MC_EN_INTR_RESP {TRUE} \
    CONFIG.MC_TRC {45750} CONFIG.MC_TRCMIN {45750} CONFIG.MC_TRCD {13750} CONFIG.MC_TRCDMIN {13750} \
    CONFIG.MC_TRP {13750} CONFIG.MC_TRPMIN {13750} CONFIG.MC_TFAW {30000} CONFIG.MC_TFAWMIN {30000} \
    CONFIG.MC_TRRD_L {11} CONFIG.MC_TRRD_L_MIN {11} CONFIG.MC_TRRD_S {9} CONFIG.MC_TRRD_S_MIN {9} \
    CONFIG.MC_F1_TRCD {13750} CONFIG.MC_F1_TRCDMIN {13750} CONFIG.MC_F1_TFAW {30000} \
    CONFIG.MC_F1_TFAWMIN {30000} CONFIG.MC_F1_TRRD_L {11} CONFIG.MC_F1_TRRD_L_MIN {11} \
    CONFIG.MC_F1_TRRD_S {9} CONFIG.MC_F1_TRRD_S_MIN {9} \
] $noc

# One CONNECTIONS entry: every value braced, or the NoC ignores the connection.
proc noc_connection {mc read_bw write_bw boot} {
    set v "read_bw {$read_bw} write_bw {$write_bw} read_avg_burst {4} write_avg_burst {4}"
    if {$boot} { append v " initial_boot {true}" }
    return "$mc {$v}"
}

# Slave port, CIPS master, its clock, MC port, read and write MB/s, category.
set i 0
foreach {si src clk mc rd wr cat} {
    S00_AXI FPD_CCI_NOC_0 fpd_cci_noc_axi0_clk MC_3 4096 4096 ps_cci
    S01_AXI FPD_CCI_NOC_1 fpd_cci_noc_axi1_clk MC_2 4096 4096 ps_cci
    S02_AXI FPD_CCI_NOC_2 fpd_cci_noc_axi2_clk MC_0 4096 4096 ps_cci
    S03_AXI FPD_CCI_NOC_3 fpd_cci_noc_axi3_clk MC_1 4096 4096 ps_cci
    S04_AXI LPD_AXI_NOC_0 lpd_axi_noc_clk      MC_3 500  500  ps_rpu
    S05_AXI PMC_NOC_AXI_0 pmc_axi_noc_axi0_clk MC_2 4096 500  ps_pmc
} {
    set_property -dict [list CONFIG.CATEGORY $cat CONFIG.CONNECTIONS [noc_connection $mc $rd $wr 1]] \
        [get_bd_intf_pins axi_noc_0/$si]
    set_property CONFIG.ASSOCIATED_BUSIF $si [get_bd_pins axi_noc_0/aclk$i]
    connect_bd_intf_net [get_bd_intf_pins ps/$src] [get_bd_intf_pins axi_noc_0/$si]
    connect_bd_net [get_bd_pins ps/$clk] [get_bd_pins axi_noc_0/aclk$i]
    incr i
}

# PL data port, pinned to the NoC master unit in clock region X1Y1, next to the static DMAs: every
# VD100 floorplan keeps X1Y1 static (boards.py). NMU sites are never part of a pblock.
set_property -dict [list CONFIG.CATEGORY {pl} CONFIG.PHYSICAL_LOC {NOC_NMU512_X0Y0} \
    CONFIG.CONNECTIONS [noc_connection MC_0 2000 2000 0]] [get_bd_intf_pins axi_noc_0/S06_AXI]
set_property CONFIG.ASSOCIATED_BUSIF S06_AXI [get_bd_pins axi_noc_0/aclk6]

create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddr4_rtl:1.0 DDR4
set sys_clk [create_bd_intf_port -mode Slave -vlnv xilinx.com:interface:diff_clock_rtl:1.0 sys_clk]
set_property CONFIG.FREQ_HZ 200000000 $sys_clk
connect_bd_intf_net [get_bd_intf_ports DDR4] [get_bd_intf_pins axi_noc_0/CH0_DDR4_0]
connect_bd_intf_net [get_bd_intf_ports sys_clk] [get_bd_intf_pins axi_noc_0/sys_clk0]

set rst_system [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_system]
connect_bd_net [get_bd_pins ps/pl0_ref_clk] [get_bd_pins rst_system/slowest_sync_clk]
connect_bd_net [get_bd_pins ps/pl0_resetn] [get_bd_pins rst_system/ext_reset_in]

set clk_net           [get_bd_pins ps/pl0_ref_clk]
set resetn_net        [get_bd_pins rst_system/peripheral_aresetn]
set resetn_ext        [get_bd_pins ps/pl0_resetn]
set gp1_intf          [get_bd_intf_pins ps/M_AXI_FPD]
set hp0_intf          [get_bd_intf_pins axi_noc_0/S06_AXI]
set versatile_clk_src ""
set gp0_intf          ""
set hp1_intf          ""
set hp1_aclk          ""

connect_bd_net $clk_net [get_bd_pins ps/m_axi_fpd_aclk]
connect_bd_net $clk_net [get_bd_pins axi_noc_0/aclk6]
