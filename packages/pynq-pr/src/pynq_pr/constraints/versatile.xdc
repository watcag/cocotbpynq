# CDC between versatile_clk (clk_fpga_1) and icap_clk (clk_fpga_2) is handled by CDC_BRIDGE in RTL
set_false_path -from [get_clocks clk_fpga_1] -to [get_clocks clk_fpga_2]
set_false_path -from [get_clocks clk_fpga_2] -to [get_clocks clk_fpga_1]
