#!/usr/bin/env python3
"""Run the §5.1 MatMul→GELU/Softmax pipeline example in simulation."""
import os
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
os.chdir(THIS_DIR)

from cocotbpynq._pr_engine import PRSystem
from cocotbpynq.pr import PRCocotbRunner


def main():
    with PRSystem(config='pr_config.yaml') as system:
        num_failed = PRCocotbRunner(
            pr_system=system,
            test_module='test_pynq',
            test_dir=str(THIS_DIR),
        ).run()
    return 1 if num_failed else 0


if __name__ == '__main__':
    sys.exit(main())
