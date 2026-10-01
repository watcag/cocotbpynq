# PS configuration for Zynq UltraScale+ (KV260).
# Enables pl_clk0 at $data_freq MHz, pl_clk1 at $versatile_freq MHz (clk_wiz input).
# The Versatile DPR controller clk_wiz doubles versatile_freq, so ICAP runs at 2x $versatile_freq MHz.
# M_AXI_HPM0/HPM1_FPD (control), S_AXI_HP0_FPD (RP data), S_AXI_HP1_FPD (bitstream fetch).
# Exports clk_net, versatile_clk_src, resetn_net, resetn_ext,
# gp0_intf, gp1_intf, hp0_intf, hp1_intf, hp1_aclk.

if { ![info exists versatile_freq] } { set versatile_freq 100 }
if { ![info exists data_freq] }      { set data_freq 100 }

set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e ps]
set_property -dict [list \
    CONFIG.PSU__FPGA_PL0_ENABLE {1} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ $data_freq \
    CONFIG.PSU__FPGA_PL1_ENABLE {1} \
    CONFIG.PSU__CRL_APB__PL1_REF_CTRL__FREQMHZ $versatile_freq \
    CONFIG.PSU__USE__M_AXI_GP0 {1} \
    CONFIG.PSU__USE__M_AXI_GP1 {1} \
    CONFIG.PSU__USE__M_AXI_GP2 {0} \
    CONFIG.PSU__USE__S_AXI_GP2 {1} \
    CONFIG.PSU__USE__S_AXI_GP3 {1} \
] $ps

set rst_system [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_system]

connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins rst_system/slowest_sync_clk]
connect_bd_net [get_bd_pins ps/pl_resetn0] [get_bd_pins rst_system/ext_reset_in]

set clk_net           [get_bd_pins ps/pl_clk0]
set versatile_clk_src [get_bd_pins ps/pl_clk1]
set resetn_net        [get_bd_pins rst_system/peripheral_aresetn]
set resetn_ext        [get_bd_pins ps/pl_resetn0]
set gp0_intf          [get_bd_intf_pins ps/M_AXI_HPM0_FPD]
set gp1_intf          [get_bd_intf_pins ps/M_AXI_HPM1_FPD]
set hp0_intf          [get_bd_intf_pins ps/S_AXI_HP0_FPD]
set hp1_intf          [get_bd_intf_pins ps/S_AXI_HP1_FPD]
set hp1_aclk          [get_bd_pins ps/saxihp1_fpd_aclk]

connect_bd_net $clk_net [get_bd_pins ps/maxihpm0_fpd_aclk]
connect_bd_net $clk_net [get_bd_pins ps/maxihpm1_fpd_aclk]
connect_bd_net $clk_net [get_bd_pins ps/saxihp0_fpd_aclk]
