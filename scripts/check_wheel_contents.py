"""Fail if a built wheel is missing a git-tracked file from its package's src/.

Usage: python scripts/check_wheel_contents.py dist/
"""
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = {"cocotbpynq": "packages/cocotbpynq/src", "pynq_pr": "packages/pynq-pr/src"}

bad = False
for wheel in sorted(Path(sys.argv[1]).glob("*.whl")):
    src = SRC[wheel.name.split("-")[0]]
    tracked = subprocess.run(["git", "ls-files", src], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.split()
    names = set(zipfile.ZipFile(wheel).namelist())
    missing = [f for f in tracked if f[len(src) + 1:] not in names]
    for f in missing:
        print(f"MISSING from {wheel.name}: {f}")
    bad |= bool(missing)
    print(f"{wheel.name}: {len(tracked)} tracked files checked")
sys.exit(1 if bad else 0)
