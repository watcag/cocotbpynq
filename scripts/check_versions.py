"""Fail unless both packages and the pynq-pr -> cocotbpynq pin share one version.

Usage: python scripts/check_versions.py [expected-version]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cp = (ROOT / "packages/cocotbpynq/pyproject.toml").read_text()
pr = (ROOT / "packages/pynq-pr/pyproject.toml").read_text()
versions = {
    "cocotbpynq": re.search(r'(?m)^version = "([^"]*)"', cp).group(1),
    "pynq-pr": re.search(r'(?m)^version = "([^"]*)"', pr).group(1),
    "pynq-pr[sim] pin": re.search(r'"cocotbpynq==([^"]*)"', pr).group(1),
}
if len(sys.argv) > 1:
    versions["expected"] = sys.argv[1]
print(versions)
sys.exit(0 if len(set(versions.values())) == 1 else "versions differ")
