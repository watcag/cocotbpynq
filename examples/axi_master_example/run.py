#!/usr/bin/env python3
"""
Run the AXI master example (memcpy_axi through an HP-port model of PS DDR) on Verilator.

Usage:
    cd examples/axi_master_example
    python run.py                     # the HP port's reset timing (8 outstanding, fixed latency)
    python run.py stress              # random read / B latency, back-pressure, beat gaps, stalls, reordering
    python run.py "r_jitter=300,reorder=1"   # any cocotbpynq.axi_mem.HpPortConfig settings

The settings reach the simulation as COCOTBPYNQ_HP (HpPortConfig.parse syntax); the
seed of the random timing is COCOTBPYNQ_AXI_SEED (default 0).
"""
import os
import sys
from pathlib import Path

from cocotb_tools.runner import get_results, get_runner
import cocotb_tools.runner as cocotb_runner

from cocotbpynq._toolchain import ensure_verilator

THIS_DIR = Path(__file__).resolve().parent
STRESS = ("r_latency=20,r_jitter=200,b_latency=10,b_jitter=100,arready_low=0.3,awready_low=0.3,wready_low=0.3,"
          "r_gap=0.3,w_before_aw=8,reorder=1,stall_rate=0.01,stall_len=50")


def main(hp: str = "", seed: int = 0, build_dir: str | None = None) -> int:
    hp = STRESS if hp == "stress" else hp
    ensure_verilator()
    jobs = int(os.environ.get("COCOTBPYNQ_BUILD_J", "1"))
    if jobs < 1:
        raise ValueError("COCOTBPYNQ_BUILD_J must be positive")
    cocotb_runner.MAX_PARALLEL_BUILD_JOBS = jobs
    build = Path(build_dir or THIS_DIR / "sim_build")
    runner = get_runner("verilator")
    runner.build(sources=[THIS_DIR / "rtl" / "memcpy_axi.v"], hdl_toplevel="memcpy_axi", build_dir=build,
                 timescale=("1ns", "1ps"), build_args=["-j", str(jobs)])
    sys.path.insert(0, str(THIS_DIR))
    results = runner.test(hdl_toplevel="memcpy_axi", test_module="test_pynq", test_dir=THIS_DIR, build_dir=build,
                          results_xml=str(build / "results.xml"),
                          extra_env={"HWH_LOCATION_DIR": str(THIS_DIR), "COCOTB_SYS_ARGV": " ".join(sys.argv),
                                     "COCOTBPYNQ_HP": hp, "COCOTBPYNQ_AXI_SEED": str(seed),
                                     "PYTHONPATH": os.pathsep.join([str(THIS_DIR), os.environ.get("PYTHONPATH", "")])})
    tests, failed = get_results(results)
    return 0 if tests > 0 and failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
