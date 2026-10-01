"""
Generates the TCL configuration file (build_config.tcl) from
the parsed YAML config and invokes Vivado to run the DFX build flow.

The build_config.tcl file contains all variables that the TCL scripts need:
project name, part, board name, sources, defines, and the list of
reconfigurable partitions with their modules and parameters.
"""

import shutil
import subprocess
from pathlib import Path

from .config import load_config, PKG_DIR
from .boards import load_board
from .floorplan import write_pblocks_xdc


def generate_tcl_config(config, board, root_dir, proj_dir, bits_dir, pblocks_xdc):
    """Generate build_config.tcl content from the parsed YAML config."""
    lines = []

    def tcl_set(var, val):
        lines.append(f'set {var} "{val}"')

    tcl_set("project_name", config["project"])
    tcl_set("reconfiguration_method", config["reconfiguration_method"])
    tcl_set("part_number", board["part"])
    tcl_set("board_part", board.get("board_part", ""))
    tcl_set("board_name", config["board"])
    tcl_set("axis_switch", "1" if config.get("axis_switch") else "0")
    tcl_set("versatile_freq", config.get("_versatile_freq", 100))
    tcl_set("data_freq", config.get("_data_freq", 100))
    tcl_set("proj_dir", str(proj_dir))
    tcl_set("bits_dir", str(bits_dir))
    tcl_set("pblocks_xdc", str(pblocks_xdc.resolve()))

    all_sources = []
    for src in config["sources"]:
        src_path = Path(src)
        resolved = str(src_path.resolve() if src_path.is_absolute() else (root_dir / src).resolve())
        if resolved not in all_sources:
            all_sources.append(resolved)

    source_list = " ".join(f'"{s}"' for s in all_sources)
    lines.append(f"set source_files [list {source_list}]")

    defines = config.get("defines", {})
    if defines:
        defines_str = " ".join(f"{k}={v}" for k, v in defines.items())
        tcl_set("verilog_defines", defines_str)
    else:
        tcl_set("verilog_defines", "")

    partitions = config["reconfigurable_partitions"]
    tcl_set("num_partitions", len(partitions))

    partition_names = " ".join(f'"{p["partition_name"]}"' for p in partitions)
    lines.append(f"set partition_names [list {partition_names}]")

    part_parts = []
    for part in partitions:
        rm_list_items = []
        for rm in part["modules"]:
            params = rm.get("parameters", {})
            if params:
                param_pairs = " ".join(f"{k} {{{v}}}" for k, v in params.items())
                params_tcl = f"[dict create {param_pairs}]"
            else:
                params_tcl = "[dict create]"
            rm_list_items.append(
                f'[dict create cell_name "{rm["cell_name"]}" '
                f'top "{rm["top"]}" '
                f"parameters {params_tcl}]"
            )

        rm_list = " ".join(rm_list_items)
        part_parts.append(
            f'    [dict create partition_name "{part["partition_name"]}" '
            f"modules [list {rm_list}]]"
        )

    lines.append("set partition_configs [list \\")
    for i, part in enumerate(part_parts):
        suffix = " \\" if i < len(part_parts) - 1 else ""
        lines.append(f"{part}{suffix}")
    lines.append("]")

    return "\n".join(lines) + "\n"


def build(config_path, force=False):
    """Load config, generate build_config.tcl, and invoke Vivado."""
    root_dir = Path.cwd()
    config = load_config(config_path)
    board = load_board(config["board"])

    proj_dir = root_dir / "output" / config["project"]

    if proj_dir.exists():
        if force:
            shutil.rmtree(proj_dir)
            print(f"Removed existing output: {proj_dir}")
        else:
            raise FileExistsError(f"Output directory already exists: {proj_dir}\nUse -f/--force to overwrite.")

    bits_dir = proj_dir / "bits"
    bits_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(config_path, proj_dir / Path(config_path).name)

    pblocks_xdc = write_pblocks_xdc(
        board, config["reconfigurable_partitions"],
        config["project"], proj_dir,
    )

    tcl_content = generate_tcl_config(config, board, root_dir, proj_dir, bits_dir, pblocks_xdc)
    config_tcl_path = proj_dir / "build_config.tcl"
    config_tcl_path.write_text(tcl_content)

    scripts_dir = Path(__file__).parent / "scripts"
    build_script = scripts_dir / "build.tcl"

    cmd = [
        "vivado", "-mode", "tcl",
        "-source", str(build_script.resolve()),
        "-tclargs", str(config_tcl_path.resolve()),
    ]

    print(f"Config written to {config_tcl_path}")
    print(f"Running Vivado...")
    subprocess.run(cmd, cwd=str(proj_dir), check=True)
    print(f"Done. Bitstreams in {bits_dir}/")


def validate_config(config_path):
    """Validate config and print a summary without running Vivado."""
    root_dir = Path.cwd()
    config = load_config(config_path)
    board = load_board(config["board"])

    print(f"Project:     {config['project']}")
    print(f"Board:       {config['board']} ({board['part']})")
    print(f"Method:      {config['reconfiguration_method']}")
    if config.get("axis_switch"):
        print(f"RP Switch:   enabled")
    print(f"Partitions:  {len(config['reconfigurable_partitions'])}")
    for part in config["reconfigurable_partitions"]:
        print(f"  {part['partition_name']}:")
        for rm in part["modules"]:
            params = rm.get("parameters", {})
            extra = f"  params={params}" if params else ""
            print(f"    {rm['cell_name']}  top={rm['top']}{extra}")
    print("Valid.")
