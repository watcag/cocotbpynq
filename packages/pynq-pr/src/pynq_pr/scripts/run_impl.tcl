# Synthesis, implementation, and bitstream generation for N partitions.

# Versal writes programmable device images (.pdi): the static one boots the board, the partial ones
# are loaded by the PMC. Zynq writes bitstreams.
if { $family eq "versal" } {
    set write_step write_device_image
    set image_ext pdi
} else {
    set write_step write_bitstream
    set image_ext bit
}

# Register all RM block designs with their partition containers
foreach part_config $partition_configs {
    set pname [dict get $part_config partition_name]
    set modules [dict get $part_config modules]

    set bd_list ""
    foreach rm $modules {
        set cn [dict get $rm cell_name]
        if { $bd_list ne "" } {
            append bd_list ":"
        }
        append bd_list "${pname}_${cn}.bd"
    }
    set_property -dict [list CONFIG.LIST_SYNTH_BD $bd_list CONFIG.LIST_SIM_BD $bd_list] \
        [get_bd_cells /${pname}/rp]
}

make_wrapper -files [get_files ${design_name}.bd] -top
set wrapper_path [file join $proj_dir ${project_name}.gen sources_1 bd $design_name hdl ${design_name}_wrapper.v]
add_files -norecurse $wrapper_path
set_property top ${design_name}_wrapper [current_fileset]
update_compile_order -fileset sources_1

generate_target all [get_files ${design_name}.bd]

# Base PR configuration: first RM in every partition
set base_partitions [list]
foreach part_config $partition_configs {
    set pname [dict get $part_config partition_name]
    set first_cn [dict get [lindex [dict get $part_config modules] 0] cell_name]
    lappend base_partitions ${design_name}_i/${pname}/rp:${pname}_${first_cn}_inst_0
}
create_pr_configuration -name config_base -partitions $base_partitions

# Variant configs: one per non-first RM, changing one partition at a time
set variant_configs [list]
foreach part_config $partition_configs {
    set pname [dict get $part_config partition_name]
    set modules [dict get $part_config modules]

    for {set i 1} {$i < [llength $modules]} {incr i} {
        set cn [dict get [lindex $modules $i] cell_name]

        set config_partitions [list]
        foreach pc $partition_configs {
            set pc_pname [dict get $pc partition_name]
            if {$pc_pname eq $pname} {
                lappend config_partitions ${design_name}_i/${pc_pname}/rp:${pname}_${cn}_inst_0
            } else {
                set pc_first [dict get [lindex [dict get $pc modules] 0] cell_name]
                lappend config_partitions ${design_name}_i/${pc_pname}/rp:${pc_pname}_${pc_first}_inst_0
            }
        }

        create_pr_configuration -name config_${pname}_${cn} -partitions $config_partitions
        lappend variant_configs ${pname}_${cn}
    }
}

set_property NAME impl_base [get_runs impl_1]
set_property PR_CONFIGURATION config_base [get_runs impl_base]

foreach vc $variant_configs {
    create_run impl_${vc} -parent_run impl_base -flow [get_property FLOW [get_runs impl_base]] -pr_config config_${vc}
}

launch_runs synth_1 -jobs $jobs
wait_on_runs synth_1
launch_runs impl_base -to_step $write_step -jobs $jobs
wait_on_run impl_base

foreach vc $variant_configs {
    launch_runs impl_${vc} -to_step $write_step -jobs $jobs
    wait_on_run impl_${vc}
}

# Copy bitstreams and hardware handoff files
file mkdir $bits_dir
set gen_bd_dir [file join $proj_dir ${project_name}.gen sources_1 bd $design_name]
set base_impl_dir [get_property DIRECTORY [get_runs impl_base]]

# Static bitstream and hwh
file copy -force [file join $base_impl_dir ${design_name}_wrapper.$image_ext] [file join $bits_dir ${project_name}.$image_ext]
file copy -force [file join $gen_bd_dir hw_handoff ${design_name}.hwh] [file join $bits_dir ${project_name}.hwh]

# First RM partials from base run
foreach part_config $partition_configs {
    set pname [dict get $part_config partition_name]
    set first_cn [dict get [lindex [dict get $part_config modules] 0] cell_name]

    file copy -force \
        [file join $base_impl_dir ${design_name}_i_${pname}_rp_${pname}_${first_cn}_inst_0_partial.$image_ext] \
        [file join $bits_dir ${pname}_${first_cn}.$image_ext]
    file copy -force \
        [file join $gen_bd_dir bd ${pname}_${first_cn}_inst_0 hw_handoff ${pname}_${first_cn}_inst_0.hwh] \
        [file join $bits_dir ${pname}_${first_cn}.hwh]
}

# Variant RM partials
foreach part_config $partition_configs {
    set pname [dict get $part_config partition_name]
    set modules [dict get $part_config modules]

    for {set i 1} {$i < [llength $modules]} {incr i} {
        set cn [dict get [lindex $modules $i] cell_name]
        set vc "${pname}_${cn}"
        set impl_dir [get_property DIRECTORY [get_runs impl_${vc}]]

        file copy -force \
            [file join $impl_dir ${design_name}_i_${pname}_rp_${pname}_${cn}_inst_0_partial.$image_ext] \
            [file join $bits_dir ${pname}_${cn}.$image_ext]
        file copy -force \
            [file join $gen_bd_dir bd ${pname}_${cn}_inst_0 hw_handoff ${pname}_${cn}_inst_0.hwh] \
            [file join $bits_dir ${pname}_${cn}.hwh]
    }
}

# Versal: rewrite the partials uncompressed (the static image stays compressed). Vivado compresses
# Versal images by default, but the PLM writes a raw partial from DDR faster than it decompresses one
# (VD100, a clock-region row: 1.9 ms raw, 9 MB, against 3.4 ms compressed, 0.5 MB).
if { $family eq "versal" } {
    # write_device_image leaves its intermediate files next to the image, so write outside bits_dir.
    # The first module of every partition comes from impl_base, every other module from its own run.
    set raw_dir [file join $proj_dir uncompressed_partials]
    file mkdir $raw_dir
    set run_cells [dict create]
    foreach part_config $partition_configs {
        set pname [dict get $part_config partition_name]
        set modules [dict get $part_config modules]
        for {set i 0} {$i < [llength $modules]} {incr i} {
            set cn [dict get [lindex $modules $i] cell_name]
            dict lappend run_cells [expr {$i == 0 ? "impl_base" : "impl_${pname}_${cn}"}] [list $pname $cn]
        }
    }
    dict for {run cells} $run_cells {
        open_run $run
        set_property BITSTREAM.GENERAL.COMPRESS FALSE [current_design]
        foreach cell $cells {
            lassign $cell pname cn
            write_device_image -force -cell ${design_name}_i/${pname}/rp [file join $raw_dir ${pname}_${cn}.pdi]
            file copy -force [file join $raw_dir ${pname}_${cn}.pdi] [file join $bits_dir ${pname}_${cn}.pdi]
        }
        close_design
    }
}

# Generate .bin files for ICAP-based reconfiguration
if { $reconfiguration_method eq "icap" } {
    # First RM partials from base run
    open_run impl_base
    foreach part_config $partition_configs {
        set pname [dict get $part_config partition_name]
        set first_cn [dict get [lindex [dict get $part_config modules] 0] cell_name]
        write_bitstream -force -cell ${design_name}_i/${pname}/rp [file join $bits_dir ${pname}_${first_cn}.bit] -bin_file
    }
    close_design

    # Variant RM partials
    foreach part_config $partition_configs {
        set pname [dict get $part_config partition_name]
        set modules [dict get $part_config modules]

        for {set i 1} {$i < [llength $modules]} {incr i} {
            set cn [dict get [lindex $modules $i] cell_name]
            set vc "${pname}_${cn}"
            open_run impl_${vc}
            write_bitstream -force -cell ${design_name}_i/${pname}/rp [file join $bits_dir ${pname}_${cn}.bit] -bin_file
            close_design
        }
    }
}
