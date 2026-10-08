#!/usr/bin/env python3
"""Simulate test_pynq.py against the example's RTL (an Alveo design, xclbin metadata from design.py).

    cd examples/cocotbpynq/alveo_example && python run.py

1. design.py writes design.xclbin (metadata only; a v++-linked xclbin of the same kernels works too).
2. cocotbpynq.xrt.make_top writes the top: the three CUs with their streams connected per the xclbin, the
   control and AXI4 master ports brought out.
3. test_pynq.py runs in cocotb: cocotbpynq.xrt.Overlay serves the AXI4 masters from an HBM model and drives
   each CU's control port.
"""
import os
import sys
from pathlib import Path

from cocotb_tools.runner import get_results, get_runner
from cocotbpynq._toolchain import ensure_verilator
from cocotbpynq.xrt import make_top, write_xclbin

import design

HERE = Path(__file__).resolve().parent
BUILD = HERE / "sim_build"


def main():
    BUILD.mkdir(exist_ok=True)
    xclbin = write_xclbin(str(BUILD / "design.xclbin"), design.XML, design.MEMS, design.CONNECTIONS)
    sources = sorted((HERE / "rtl").glob("*.sv"))
    top = make_top(xclbin, sources, BUILD / "xrt_top.sv")
    ensure_verilator()
    runner = get_runner("verilator")
    runner.build(sources=sources + [BUILD / "xrt_top.sv"], hdl_toplevel=top, build_dir=BUILD, always=True,
                 timescale=("1ns", "1ps"), build_args=["-Wno-fatal"])
    results = runner.test(hdl_toplevel=top, test_module="test_pynq", build_dir=BUILD, test_dir=HERE,
                          extra_env={"COCOTB_SYS_ARGV": xclbin})
    return 1 if get_results(results)[1] else 0


if __name__ == "__main__":
    sys.exit(main())
