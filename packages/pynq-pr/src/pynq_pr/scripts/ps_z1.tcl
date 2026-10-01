# PS configuration for Zynq-7000 (Z1).
# Enables FCLK0 at $data_freq MHz, FCLK1 at $versatile_freq MHz (clk_wiz input).
# The Versatile DPR controller clk_wiz doubles versatile_freq, so ICAP runs at 2x $versatile_freq MHz.
# M_AXI_GP0/GP1 (control), S_AXI_HP0 (RP data), S_AXI_HP1 (bitstream fetch).
# Exports clk_net, versatile_clk_src, resetn_net, resetn_ext,
# gp0_intf, gp1_intf, hp0_intf, hp1_intf, hp1_aclk.

create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddrx_rtl:1.0 DDR
create_bd_intf_port -mode Master -vlnv xilinx.com:display_processing_system7:fixedio_rtl:1.0 FIXED_IO

if { ![info exists versatile_freq] } { set versatile_freq 100 }
if { ![info exists data_freq] }      { set data_freq 100 }

set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps]
set_property -dict [list \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ $data_freq \
    CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ $versatile_freq \
    CONFIG.PCW_FPGA_FCLK0_ENABLE {1} \
    CONFIG.PCW_FPGA_FCLK1_ENABLE {1} \
    CONFIG.PCW_EN_CLK1_PORT {1} \
    CONFIG.PCW_FCLK_CLK1_BUF {TRUE} \
    CONFIG.PCW_USE_M_AXI_GP1 {1} \
    CONFIG.PCW_USE_S_AXI_HP0 {1} \
    CONFIG.PCW_USE_S_AXI_HP1 {1} \
] $ps

set rst_system [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_system]

connect_bd_intf_net [get_bd_intf_ports DDR] [get_bd_intf_pins ps/DDR]
connect_bd_intf_net [get_bd_intf_ports FIXED_IO] [get_bd_intf_pins ps/FIXED_IO]

connect_bd_net [get_bd_pins ps/FCLK_CLK0] [get_bd_pins rst_system/slowest_sync_clk]
connect_bd_net [get_bd_pins ps/FCLK_RESET0_N] [get_bd_pins rst_system/ext_reset_in]

set clk_net           [get_bd_pins ps/FCLK_CLK0]
set versatile_clk_src [get_bd_pins ps/FCLK_CLK1]
set resetn_net        [get_bd_pins rst_system/peripheral_aresetn]
set resetn_ext        [get_bd_pins ps/FCLK_RESET0_N]
set gp0_intf          [get_bd_intf_pins ps/M_AXI_GP0]
set gp1_intf          [get_bd_intf_pins ps/M_AXI_GP1]
set hp0_intf          [get_bd_intf_pins ps/S_AXI_HP0]
set hp1_intf          [get_bd_intf_pins ps/S_AXI_HP1]
set hp1_aclk          [get_bd_pins ps/S_AXI_HP1_ACLK]

connect_bd_net $clk_net [get_bd_pins ps/M_AXI_GP0_ACLK]
connect_bd_net $clk_net [get_bd_pins ps/M_AXI_GP1_ACLK]
connect_bd_net $clk_net [get_bd_pins ps/S_AXI_HP0_ACLK]
