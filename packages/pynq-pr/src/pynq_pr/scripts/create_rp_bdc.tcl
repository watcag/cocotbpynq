# Wrap each partition's dummy into a BDC and replace with the first RM.
current_bd_design $design_name
current_bd_instance /

foreach part_config $partition_configs {
    set pname [dict get $part_config partition_name]
    set modules [dict get $part_config modules]
    set first_rm [lindex $modules 0]
    set first_rm_name [dict get $first_rm cell_name]
    set first_rm_top [dict get $first_rm top]
    set first_rm_params [dict get $first_rm parameters]

    current_bd_design $design_name
    current_bd_instance /${pname}

    group_bd_cells dummy_hier [get_bd_cells dummy]

    current_bd_instance /
    validate_bd_design
    save_bd_design

    create_bd_design -cell [get_bd_cells /${pname}/dummy_hier] ${pname}_${first_rm_name}
    validate_bd_design
    save_bd_design

    current_bd_design $design_name
    current_bd_instance /${pname}

    set new_cell [create_bd_cell -type container -reference ${pname}_${first_rm_name} ${pname}_temp]
    replace_bd_cell [get_bd_cells dummy_hier] $new_cell
    delete_bd_objs [get_bd_cells dummy_hier]
    set_property name rp $new_cell

    current_bd_instance /

    update_compile_order -fileset sources_1
    validate_bd_design
    save_bd_design

    current_bd_design [get_bd_designs ${pname}_${first_rm_name}]

    delete_bd_objs [get_bd_cells dummy]
    set cell [create_bd_cell -type module -reference $first_rm_top $first_rm_top]

    utils::apply_rm_params $cell $first_rm_params
    utils::connect_rm_ports $first_rm_top

    validate_bd_design
    save_bd_design

    current_bd_design [get_bd_designs $design_name]
    upgrade_bd_cells [get_bd_cells /${pname}/rp]
    validate_bd_design
    save_bd_design
}
