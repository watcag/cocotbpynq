# Enable DFX (Dynamic Function eXchange) on the project and all BDCs.
set_property PR_FLOW 1 [current_project]
current_bd_design [get_bd_designs $design_name]

foreach part_config $partition_configs {
    set pname [dict get $part_config partition_name]
    set_property -dict [list CONFIG.ENABLE_DFX {true}] [get_bd_cells /${pname}/rp]
    set_property -dict [list CONFIG.LOCK_PROPAGATE {true}] [get_bd_cells /${pname}/rp]
}

validate_bd_design
save_bd_design
