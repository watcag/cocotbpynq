#!/usr/bin/env python3
"""
Standalone cocotbpynq simulation runner.

Usage:
    python3 -m pynq_pr.run --config sim/tutorial_z1/pr_sim.yaml --test pr_min_test
    python3 -m pynq_pr.run --config sim/tutorial_z1/pr_sim.yaml --test pr_min_test.py
    python3 run.py --config pr_sim.yaml --test pr_min_test
"""
import argparse
import sys
import os
import shutil
from pathlib import Path


def _resolve_test_target(test, default_test_dir, config_dir):
    """Resolve a cocotb test target to (module_name, test_dir)."""
    default_dir = Path(default_test_dir).resolve()
    config_dir = Path(config_dir).resolve()

    looks_like_path = test.endswith(".py") or any(
        sep and sep in test for sep in (os.sep, os.altsep)
    )
    if not looks_like_path:
        return test, str(default_dir)

    raw_path = Path(test)
    candidates = [raw_path] if raw_path.is_absolute() else [
        default_dir / raw_path,
        config_dir / raw_path,
    ]

    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate.exists() and candidate.is_file():
            if candidate.suffix != ".py":
                print(f"Test file must be a .py file: {candidate}", file=sys.stderr)
                return None, None
            return candidate.stem, str(candidate.parent)

    print(f"Test file not found: {test}", file=sys.stderr)
    return None, None


def run_simulation(config, test, test_dir=None):
    """Run a cocotbpynq simulation.

    Args:
        config: path to cocotbpynq pr_sim.yaml
        test: Python test module name or path to a .py file
        test_dir: directory containing the test module (defaults to cwd)
    """
    config_path = Path(config).resolve()
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    if test_dir is None:
        test_dir = str(Path.cwd().resolve())

    test_module, test_dir = _resolve_test_target(test, test_dir, config_path.parent)
    if test_module is None:
        return 1

    # cocotbpynq resolves paths relative to cwd, so cd to config dir
    os.chdir(config_path.parent)

    from cocotbpynq._pr_engine import PRSystem
    from cocotbpynq.pr import PRCocotbRunner

    with PRSystem(config=str(config_path)) as system:
        print("Building RM binaries (cocotb mode)...")
        system.build(cocotb_mode=True)
        print("Build complete.")

        print("Running cocotbpynq simulation...")
        runner = PRCocotbRunner(
            pr_system=system,
            test_module=test_module,
            test_dir=test_dir,
        )

        project_hwh_name = config_path.parent.name
        if project_hwh_name != "design":
            original_generate_hwh = runner._generate_hwh

            def _generate_hwh_with_project_alias(build_dir):
                hwh_dir = Path(original_generate_hwh(build_dir)).resolve()
                design_hwh = hwh_dir / "design.hwh"
                project_hwh = hwh_dir / f"{project_hwh_name}.hwh"
                shutil.copyfile(design_hwh, project_hwh)
                return hwh_dir

            runner._generate_hwh = _generate_hwh_with_project_alias

        num_failed = runner.run()
        print("Done.")

    return 1 if num_failed else 0


def main():
    parser = argparse.ArgumentParser(description="Run cocotbpynq PR simulation")
    parser.add_argument("-c", "--config", required=True,
                        help="Path to cocotbpynq pr_sim.yaml")
    parser.add_argument("-t", "--test", required=True,
                        help="Python test module name or path to a .py file")
    args = parser.parse_args()
    return run_simulation(args.config, args.test)


if __name__ == '__main__':
    sys.exit(main())
