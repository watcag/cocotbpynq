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
    proc connect_rm_ports { rm_top } {
        set intf_port_names [list]
        foreach intf [get_bd_intf_ports] {
            set name [get_property NAME $intf]
            connect_bd_intf_net [get_bd_intf_ports $name] -boundary_type upper [get_bd_intf_pins $rm_top/$name]
            foreach sub_port [get_bd_ports ${name}_*] {
                lappend intf_port_names [get_property NAME $sub_port]
            }
        }

        foreach port [get_bd_ports] {
            set name [get_property NAME $port]
            if {[lsearch -exact $intf_port_names $name] == -1} {
                connect_bd_net [get_bd_ports $name] [get_bd_pins $rm_top/$name]
            }
        }
    }
}
