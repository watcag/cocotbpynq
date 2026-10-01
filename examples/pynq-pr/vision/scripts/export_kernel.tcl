foreach var {HLS_TOP_NAME HLS_SRC_FILE HLS_PROJECT_ROOT HLS_RTL_ROOT HLS_PART_NAME HLS_CLOCK_NS} {
    if {![info exists ::env($var)]} {
        puts stderr "missing required environment variable: $var"
        exit 1
    }
}

set top_name     $::env(HLS_TOP_NAME)
set src_file     [file normalize $::env(HLS_SRC_FILE)]
set project_root [file normalize $::env(HLS_PROJECT_ROOT)]
set rtl_root     [file normalize $::env(HLS_RTL_ROOT)]
set part_name    $::env(HLS_PART_NAME)
set clock_ns     $::env(HLS_CLOCK_NS)

set script_dir [file dirname [info script]]
set src_dir    [file normalize [file join $script_dir .. hls src]]

if {![info exists ::env(VITIS_LIBRARIES)]} {
    puts stderr "VITIS_LIBRARIES is not set"
    exit 1
}

set vitis_libraries [file normalize $::env(VITIS_LIBRARIES)]
set vision_include  [file join $vitis_libraries vision L1 include]

if {![file exists $vision_include]} {
    puts stderr "Vitis Vision include directory not found: $vision_include"
    exit 1
}

file mkdir $project_root
cd $project_root
open_project -reset $top_name
set_top $top_name
add_files $src_file -cflags "-std=c++14 -I$src_dir -I$vision_include"
open_solution -reset solution1
set_part $part_name
create_clock -period $clock_ns -name default
config_rtl -reset_level low
csynth_design
export_design -rtl verilog -format ip_catalog
exit
