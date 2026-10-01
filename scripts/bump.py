"""Set the release version of both packages and the pynq-pr -> cocotbpynq pin.

Usage: python scripts/bump.py 0.2.0
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECTS = [ROOT / "packages/cocotbpynq/pyproject.toml", ROOT / "packages/pynq-pr/pyproject.toml"]


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+((a|b|rc)\d+|\.dev\d+)?", sys.argv[1]):
        sys.exit(__doc__)
    version = sys.argv[1]
    for path in PYPROJECTS:
        text = path.read_text()
        new = re.sub(r'(?m)^version = "[^"]*"', f'version = "{version}"', text, count=1)
        new = re.sub(r'"cocotbpynq==[^"]*"', f'"cocotbpynq=={version}"', new)
        if new != text:
            path.write_text(new)
            print(f"{path.relative_to(ROOT)}: {version}")


if __name__ == "__main__":
    main()
