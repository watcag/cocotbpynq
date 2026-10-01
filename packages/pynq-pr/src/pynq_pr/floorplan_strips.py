"""
Generates pblock constraints (XDC) that partition the reconfigurable area
across N reconfigurable partitions.

The reconfigurable area is a single rectangle defined per board in boards.py.
It is split into N equal-height horizontal strips, where each strip spans
the full width of the rectangle.

Why full-width horizontal strips?
  DSPs, BRAMs, and URAMs are concentrated in specific columns of the FPGA
  fabric. If we split by columns, some partitions would end up without
  BRAMs or DSPs entirely. Full-width strips guarantee that every partition
  gets proportional access to all resource types.

SNAPPING_MODE ON is set on each pblock so that Vivado snaps the boundaries
to valid DFX configuration frame edges at implementation time.

To change the reconfigurable area or add a board, edit the
reconfigurable_area dict in boards.py.
"""

from pathlib import Path


def generate_pblocks_xdc(board, partitions, design_name):
    """
    Generate XDC pblock constraints for N partitions.

    Args:
        board: board dict from boards.py
        partitions: list of partition dicts from the YAML config
        design_name: BD design name (used for cell paths)

    Returns:
        XDC content as a string.
    """
    area = board["reconfigurable_area"]
    n = len(partitions)

    sx_min, sx_max, sy_min, sy_max = area["SLICE"]
    total_height = sy_max - sy_min + 1
    base_height = total_height // n
    extra_rows = total_height % n

    lines = []
    y_cursor = sy_min

    for i, part in enumerate(partitions):
        pname = part["partition_name"]

        h = base_height + (1 if i < extra_rows else 0)
        py_min = y_cursor
        py_max = y_cursor + h - 1
        y_cursor = py_max + 1

        lines.append(f"create_pblock pblock_{pname}")
        lines.append(
            f"add_cells_to_pblock [get_pblocks pblock_{pname}] "
            f"[get_cells -quiet [list {design_name}_i/{pname}/rp]]"
        )
        lines.append(
            f"resize_pblock pblock_{pname} -add "
            f"{{SLICE_X{sx_min}Y{py_min}:SLICE_X{sx_max}Y{py_max}}}"
        )

        for res_type, (rx_min, rx_max, ry_min, ry_max) in area.items():
            if res_type == "SLICE":
                continue
            res_height = ry_max - ry_min + 1
            rpy_min = ry_min + int((py_min - sy_min) / total_height * res_height)
            rpy_max = ry_min + int((py_max - sy_min + 1) / total_height * res_height) - 1
            lines.append(
                f"resize_pblock pblock_{pname} -add "
                f"{{{res_type}_X{rx_min}Y{rpy_min}:{res_type}_X{rx_max}Y{rpy_max}}}"
            )

        lines.append(f"set_property RESET_AFTER_RECONFIG true [get_pblocks pblock_{pname}]")
        lines.append(f"set_property SNAPPING_MODE ON [get_pblocks pblock_{pname}]")
        lines.append("")

    return "\n".join(lines)


def write_pblocks_xdc(board, partitions, design_name, output_dir):
    """Generate and write pblocks.xdc to the output directory."""
    xdc_content = generate_pblocks_xdc(board, partitions, design_name)
    xdc_path = Path(output_dir) / "pblocks.xdc"
    xdc_path.write_text(xdc_content)
    return xdc_path
