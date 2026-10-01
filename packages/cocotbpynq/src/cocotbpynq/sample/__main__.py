import shutil
import sys
from pathlib import Path


def main():
    has_sim_build = Path("sim_build").is_dir()

    from cocotbpynq.sample.cocotb_runner import main as run
    rc = run()

    if not has_sim_build: # Don't delete sim_build dir if it was pre-existing
        shutil.rmtree("sim_build", ignore_errors=True)
    return rc

if __name__ == "__main__":
    sys.exit(main())
