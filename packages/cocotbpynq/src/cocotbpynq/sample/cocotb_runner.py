from pathlib import Path
from cocotb_tools.runner import get_results, get_runner
import os
import sys
from cocotbpynq._toolchain import ensure_verilator
projdir = Path(__file__).resolve().parent # Set projdir to "sample" folder

RUNNER = os.environ.get("SIM", "verilator") # Simulator (e.g. SIM=icarus)
TOP="poly" # Toplevel verilog module name
SOURCES=[projdir / "poly_axi.v", projdir / "poly_AXILiteS_s_axi.v"] # List of
TEST_MODULE = "cocotbpynq.sample.adapted" # Importable from anywhere, so outputs can go to the cwd
HWH_LOCATION_DIR = projdir
SYS_ARGV=" ".join(sys.argv)

def main():
    if RUNNER == "verilator":
        ensure_verilator()
    runner = get_runner(RUNNER)
    runner.build(
        sources=SOURCES,
        hdl_toplevel=TOP,
        always=True,
        build_args=[],
        parameters={},
        timescale = ('1ns', '1ps'),
        waves=True
    )

    # test_dir defaults to the build dir (./sim_build), never the installed package dir
    results_xml = runner.test(
        hdl_toplevel=TOP,
        hdl_toplevel_lang="verilog",
        test_module=[TEST_MODULE],
        test_args=[],
        extra_env={
            "HWH_LOCATION_DIR": HWH_LOCATION_DIR,
            "COCOTB_SYS_ARGV": SYS_ARGV # Optionally pass commandline arguments to adapted.py as os.getenv("COCOTB_SYS_ARGV")
        },
        waves=True
    )
    _, num_failed = get_results(results_xml)
    return 1 if num_failed else 0

if __name__ == "__main__":
    sys.exit(main())
