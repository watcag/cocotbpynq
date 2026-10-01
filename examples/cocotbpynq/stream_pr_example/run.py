#!/usr/bin/env python3
"""
Run the streaming PR + cocotbpynq DMA integration example.

Usage:
    cd examples/cocotbpynq/stream_pr_example
    uv run python run.py

What happens:
  1. Build RM binaries (cocotb_mode=True).
  2. Generate a HWH file so cocotbpynq discovers the AXI-Stream DMA.
  3. Start RM processes, launch cocotb simulation.
  4. test_pynq.py streams data via DMA, reconfigures RM, verifies.
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
