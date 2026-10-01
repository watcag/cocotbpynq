#!/usr/bin/env python3
"""
Run the AXI-Stream switch PR example.

Usage:
    cd examples/switch_pr_example
    uv run python run.py
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
