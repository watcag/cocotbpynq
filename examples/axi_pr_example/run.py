#!/usr/bin/env python3
"""
Run the AXI PR + cocotbpynq integration example.

Usage:
    cd examples/axi_pr_example
    uv run python run.py

What happens:
  1. Build RM binaries only (cocotb_mode=True -- no static binary needed).
  2. Generate a HWH file from pr_config.yaml so cocotbpynq can discover
     the AXI-Lite slave (MMIO at 0x43C00000).
  3. Start RM processes, launch cocotb simulation.
  4. cocotb drives the static region clock via VPI; the AXI-Lite slave
     in compute_static.sv is driven by cocotbpynq MMIO.
  5. test_pynq.py runs: writes data_in, reads result, reconfigures RM,
     verifies result changes.
"""
import sys
import os
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
os.chdir(THIS_DIR)

from cocotbpynq._pr_engine import PRSystem
from cocotbpynq.pr import PRCocotbRunner


def main():
    with PRSystem(config='pr_config.yaml') as system:
        print("Building RM binaries (cocotb mode)...")
        system.build(cocotb_mode=True)
        print("Build complete.")

        print("Running cocotbpynq simulation...")
        runner = PRCocotbRunner(
            pr_system=system,
            test_module='test_pynq',
            test_dir=str(THIS_DIR),
        )
        num_failed = runner.run()
        print("Done.")
    return 1 if num_failed else 0


if __name__ == '__main__':
    sys.exit(main())
