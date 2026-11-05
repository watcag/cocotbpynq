# Utility procs shared across pynq-pr TCL scripts.

namespace eval utils {

    # Apply Verilog parameters to a BD cell.
    proc apply_rm_params { cell params } {
        if { [dict size $params] > 0 } {
            set prop_list [list]
            dict for {key val} $params {
                lappend prop_list "CONFIG.$key" "$val"
            }
            set_property -dict $prop_list $cell
        }
    }

    # Connect an RM module's ports to the BDC boundary.
    # Connects interface ports (AXI-Stream, AXI-Lite, etc.) first,
    # then connects remaining scalar ports (clk, rst_n) while
    # skipping individual signals that belong to an interface.
    # The NoC input (noc_interconnect) is wired inside the RM by add_noc_input, so it is skipped.
    proc connect_rm_ports { rm_top } {
        set intf_port_names [list]
        foreach intf [get_bd_intf_ports] {
            set name [get_property NAME $intf]
            foreach sub_port [get_bd_ports ${name}_*] {
                lappend intf_port_names [get_property NAME $sub_port]
            }
            if { [string match xilinx.com:interface:inis_rtl:* [get_property VLNV $intf]] } {
                continue
            }
            if { [get_bd_intf_pins -quiet $rm_top/$name] eq "" } {
                error "pynq-pr: module $rm_top has no $name interface (see the RTL interface requirements)"
            }
            connect_bd_intf_net [get_bd_intf_ports $name] -boundary_type upper [get_bd_intf_pins $rm_top/$name]
        }

        foreach port [get_bd_ports] {
            set name [get_property NAME $port]
            if {[lsearch -exact $intf_port_names $name] == -1} {
                connect_bd_net [get_bd_ports $name] [get_bd_pins $rm_top/$name]
            }
        }
    }

    # QoS of one NoC stream connection (noc_interconnect): every 32-bit word takes a 128-bit NoC beat,
    # so a stream at data_freq MHz moves 16 bytes per cycle through the NoC.
    proc noc_stream_qos {} {
        set bw [expr {16 * $::data_freq}]
        return "read_bw {0} write_bw {$bw} read_avg_burst {4} write_avg_burst {4}"
    }

    # NoC input of a partition (noc_interconnect): an NSU inside the RM, which the PLM quiesces
    # while the partition is reconfigured, and the 128-bit NoC stream narrowed to the module's x.
    # Returns the narrowed stream.
    proc add_noc_input { ini clk } {
        set rx [create_bd_cell -type ip -vlnv xilinx.com:ip:axis_noc noc_rx]
        set_property -dict [list CONFIG.NUM_SI 0 CONFIG.NUM_MI 1 CONFIG.NUM_NSI 1 CONFIG.NUM_NMI 0 \
            CONFIG.NUM_CLKS 1] $rx
        set_property -dict [list CONFIG.INI_STRATEGY load CONFIG.CONNECTIONS [list M00_AXIS [noc_stream_qos]]] \
            [get_bd_intf_pins noc_rx/S00_INIS]
        create_bd_cell -type module -reference noc_stream_narrow noc_narrow
        connect_bd_intf_net $ini [get_bd_intf_pins noc_rx/S00_INIS]
        connect_bd_intf_net [get_bd_intf_pins noc_rx/M00_AXIS] [get_bd_intf_pins noc_narrow/s_axis]
        connect_bd_net $clk [get_bd_pins noc_rx/aclk0] [get_bd_pins noc_narrow/clk]
        return [get_bd_intf_pins noc_narrow/m_axis]
    }

    # Fill the current (empty) RM block design: the module with its parameters, the NoC input in
    # noc_interconnect mode, and the boundary connections.
    proc populate_rm { rm_top params } {
        set cell [create_bd_cell -type module -reference $rm_top $rm_top]
        apply_rm_params $cell $params
        if { $::noc_interconnect eq "1" } {
            set ini [get_bd_intf_ports -filter {VLNV =~ "xilinx.com:interface:inis_rtl:*"}]
            set x [add_noc_input $ini [get_bd_ports clk]]
            connect_bd_intf_net $x [get_bd_intf_pins $rm_top/x]
        }
        connect_rm_ports $rm_top
        # An unconnected module pin would leave the partition empty after synthesis, silently.
        foreach pin [concat [get_bd_intf_pins $rm_top/*] [get_bd_pins -filter {INTF != TRUE} $rm_top/*]] {
            set net [expr {[get_property CLASS $pin] eq "bd_intf_pin" ? [get_bd_intf_nets -quiet -of_objects $pin] : [get_bd_nets -quiet -of_objects $pin]}]
            if { $net eq "" } {
                error "pynq-pr: $pin of module $rm_top is not connected to the partition boundary"
            }
        }
    }
}
