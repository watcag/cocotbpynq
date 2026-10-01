#!/usr/bin/env python3
"""
Run the video processing pipeline PR example.

6 reconfigurable stages × 4 RM variants per stage = 24 RM binaries that
compose 4,096 distinct pipelines at runtime. The Pynq side streams a
64x64 RGB image through whatever chain is programmed and saves the
result as a .ppm.

Usage:
    cd examples/cocotbpynq/video_pipeline_pr_example
    uv run python run.py
"""
import os
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
os.chdir(THIS_DIR)

from cocotbpynq._pr_engine import PRSystem
from cocotbpynq.pr import PRCocotbRunner


def main():
    with PRSystem(config='pr_config.yaml') as system:
        print("Building 24 RM binaries (cocotb mode)...")
        system.build(cocotb_mode=True)
        print("Build complete.")

        runner = PRCocotbRunner(
            pr_system=system,
            test_module='test_pynq',
            test_dir=str(THIS_DIR),
        )
        num_failed = runner.run()
    return 1 if num_failed else 0


if __name__ == '__main__':
    sys.exit(main())
