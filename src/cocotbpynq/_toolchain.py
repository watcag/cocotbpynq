# cocotbpynq - a cocotb based emulation tool for PYNQ-targetting code
# Copyright (C) 2025 Gavin Lusby and Nachiket Kapre
# Developed at WatCAG, University of Waterloo

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Simulator toolchain checks shared by the sample runner and the PR engine."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MIN_VERILATOR = (5, 36)  # cocotb 2.x supports Verilator 5.036+

INSTALL_HINT = (
    "Install Verilator >= 5.036 with one of:\n"
    "  pip install verilator          (Linux x86-64 / macOS; cocotbpynq finds it automatically)\n"
    "  brew install verilator         (macOS)\n"
    "  the YosysHQ oss-cad-suite tarball (https://github.com/YosysHQ/oss-cad-suite-build)\n"
    "Distribution packages (apt) are too old for cocotb 2.x."
)


def _add_pip_verilator_to_path():
    """The PyPI 'verilator' wheel ships a real verilator in <pkg>/bin but only
    exposes a 'verilator-cli' console script, so put its bin/ on PATH."""
    try:
        import verilator
    except ImportError:
        return
    bin_dir = Path(verilator.__file__).resolve().parent / "bin"
    if (bin_dir / "verilator").exists():
        # Its makefiles call a bare `python`; use this interpreter's bin/ (a
        # venv always has `python`) even if the venv was not activated.
        paths = [str(bin_dir), str(Path(sys.executable).parent)]
        os.environ["PATH"] = os.pathsep.join(paths + [os.environ.get("PATH", "")])


def ensure_verilator(min_version=MIN_VERILATOR):
    """Make sure a recent enough verilator is on PATH, or exit with a clear message."""
    if shutil.which("verilator") is None:
        _add_pip_verilator_to_path()
    if shutil.which("verilator") is None:
        sys.exit("cocotbpynq: verilator not found on PATH.\n" + INSTALL_HINT)
    out = subprocess.run(["verilator", "--version"], capture_output=True, text=True).stdout
    m = re.search(r"Verilator (\d+)\.(\d+)", out)
    if m and (int(m.group(1)), int(m.group(2))) < min_version:
        sys.exit(f"cocotbpynq: found {out.strip()}, but cocotb 2.x needs "
                 f"Verilator >= {min_version[0]}.{min_version[1]:03d}.\n" + INSTALL_HINT)
    _fix_pch_include_flag()


def _fix_pch_include_flag():
    """Some Verilator builds (e.g. the PyPI 'verilator' 5.48.0 wheel) ship a
    verilated.mk with an empty CFG_CXXFLAGS_PCH_I, so precompiled headers are
    passed to the compiler as input files and larger designs fail to build.
    Supply the flag through MAKEFLAGS, which also reaches sub-makes."""
    root = subprocess.run(["verilator", "--getenv", "VERILATOR_ROOT"],
                          capture_output=True, text=True).stdout.strip()
    mk = Path(root) / "include" / "verilated.mk"
    try:
        text = mk.read_text()
    except OSError:
        return
    if re.search(r"^CFG_CXXFLAGS_PCH_I\s*=\s*$", text, re.M):
        flags = os.environ.get("MAKEFLAGS", "")
        if "CFG_CXXFLAGS_PCH_I" not in flags:
            os.environ["MAKEFLAGS"] = (flags + " CFG_CXXFLAGS_PCH_I=-include").strip()
