"""Every board in pynq_pr.boards must be complete and floorplan every partition count it supports.

Adding a board means adding an entry to BOARDS and a scripts/ps_<board>.tcl;
this test checks both for every board, so a new board is covered automatically.
"""
import re
from importlib.resources import files

import pytest

from pynq_pr.boards import BOARDS
from pynq_pr.floorplan import generate_pblocks_xdc

MAX_PARTITIONS = 4  # pynq_pr.config accepts 1-4 partitions; a board with layouts lists its own


@pytest.mark.parametrize("name", sorted(BOARDS))
def test_board_is_complete_and_floorplans(name):
    board = BOARDS[name]
    assert board["family"] in ("zynq", "versal")
    # Zynq-7000 has ICAPE2, Zynq UltraScale+ ICAPE3; Versal has no ICAP (the PMC loads partials)
    assert board["icap_primitive"] in (("ICAPE2", "ICAPE3") if board["family"] == "zynq" else (None,))
    assert files("pynq_pr").joinpath("scripts", f"ps_{name}.tcl").is_file(), \
        f"missing scripts/ps_{name}.tcl"

    counts = sorted(board["layouts"]) if "layouts" in board else range(1, MAX_PARTITIONS + 1)
    assert counts and min(counts) == 1 and max(counts) <= MAX_PARTITIONS
    for n in counts:
        partitions = [{"partition_name": f"rp{i}"} for i in range(n)]
        xdc = generate_pblocks_xdc(board, partitions, "design")

        regions_per_partition = {}
        for pname, regions in re.findall(
                r"resize_pblock pblock_(\w+) -add .*get_clock_regions \{([^}]*)\}", xdc):
            regions_per_partition[pname] = regions.split()
        assert sorted(regions_per_partition) == sorted(p["partition_name"] for p in partitions)

        used = [r for regions in regions_per_partition.values() for r in regions]
        assert all(regions_per_partition.values()), f"{n} partitions: an empty pblock"
        assert len(used) == len(set(used)), f"{n} partitions: a clock region is used twice"
        assert set(used) <= set(board["clock_regions"]), f"{n} partitions: unknown clock region"
