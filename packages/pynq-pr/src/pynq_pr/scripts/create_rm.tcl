# Create additional reconfigurable modules (index 1+) for each partition.
foreach part_config $partition_configs {
    set pname [dict get $part_config partition_name]
    set modules [dict get $part_config modules]
    set num_rms [llength $modules]

    for {set i 1} {$i < $num_rms} {incr i} {
        set rm [lindex $modules $i]
        set rm_cell_name [dict get $rm cell_name]
        set rm_top [dict get $rm top]
        set rm_params [dict get $rm parameters]

        current_bd_design [get_bd_designs $design_name]
        create_bd_design -boundary_from_container [get_bd_cells /${pname}/rp] ${pname}_${rm_cell_name}

        set cell [create_bd_cell -type module -reference $rm_top $rm_top]

        utils::apply_rm_params $cell $rm_params
        utils::connect_rm_ports $rm_top

        validate_bd_design
        save_bd_design

        current_bd_design [get_bd_designs $design_name]
        validate_bd_design
        save_bd_design
    }
}
