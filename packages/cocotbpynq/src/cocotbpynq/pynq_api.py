# cocotbpynq - a cocotb based emulation tool for PYNQ-targetting code
# Copyright (C) 2026 WatCAG, University of Waterloo

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

"""The PYNQ release the simulation behaves as, for embedded (Zynq/ZynqMP) boards.

``COCOTBPYNQ_PYNQ_VERSION`` selects it: ``4.0.0`` (default) or ``3.0.1``.  PYNQ 4.0
differs where host code can notice:

* ``pynq.ps.ON_TARGET`` is ``os.path.isfile('/proc/device-tree/chosen/pynq_board')``.
  Off target, PYNQ never imports ``pyxrt``, so the first ``Overlay``, ``allocate`` or
  ``MMIO`` (anything that opens ``Device.active_device``) raises
  ``NameError: name 'pyxrt' is not defined``.  The simulated board's device tree is
  ``COCOTBPYNQ_DEVICE_TREE`` (a directory standing for ``/proc/device-tree``, e.g. a copy
  of the board's ``chosen`` node); unset, it is a board with ``chosen/pynq_board``.
* Every image load (``Overlay`` download, partial download) writes ``loaded.xclbin``
  into the host process's current directory (``pynq/pl_server/xrt_device.py:_xrt_download``).
  The simulation writes the same file in the cocotb test's current directory.
* A synced slice of a buffer syncs the whole buffer object (``bo.sync`` takes no range),
  buffers are at least 8 KiB, and ``freebuffer`` unmaps the buffer.
* ``DMA`` channels drop ``_active_buffer`` after ``wait()``.
* ``buffer.flush()``/``invalidate()`` call ``bo.sync(direction)`` (pl_server/xrt_device.py), an overload
  pyxrt has only from XRT 2023.2 (2.16).  ``COCOTBPYNQ_PYXRT`` is the simulated board's pyxrt version,
  default ``2.16.204`` (XRT 2023.2).  An image with an older XRT, e.g. ``2.13.479`` (Kria-PYNQ on the
  KV260, whose pyxrt has only ``sync(direction, size, offset)``), makes
  every flush or invalidate (and so every DMA transfer) raise ``RuntimeError: Buffer Flush Failed: sync(): incompatible function
  arguments ...`` (``Buffer Invalidate Failed``), as on the board.

Alveo cards (``cocotbpynq.xrt``) follow watcag/PYNQ's XrtNativeDevice instead, which loads
an xclbin from its path and is not gated on ``ON_TARGET``.
"""

import os

VERSION = os.environ.get("COCOTBPYNQ_PYNQ_VERSION", "4.0.0")
SUPPORTED = ("3.0.1", "4.0.0")
if VERSION not in SUPPORTED:
    raise ImportError(f"COCOTBPYNQ_PYNQ_VERSION={VERSION!r}: cocotbpynq simulates PYNQ {' or '.join(SUPPORTED)}")
PYNQ4 = VERSION.split(".")[0] == "4"

# The simulated board's pyxrt.  Default: one with bo.sync(direction), which PYNQ 4.0 needs.  Give the
# board's XRT version (e.g. 2.13.479 for the KV260's image) to reproduce an older pyxrt.
PYXRT = os.environ.get("COCOTBPYNQ_PYXRT", "2.16.204")
try:
    _PYXRT_VERSION = tuple(int(p) for p in PYXRT.split("."))
except ValueError:
    raise ImportError(f"COCOTBPYNQ_PYXRT={PYXRT!r}: give the board's XRT version, e.g. 2.13.479") from None
if len(_PYXRT_VERSION) < 2:
    raise ImportError(f"COCOTBPYNQ_PYXRT={PYXRT!r}: give at least major.minor")
PYXRT_WHOLE_SYNC = _PYXRT_VERSION >= (2, 16)      # pyxrt.bo.sync(direction): XRT 2023.2 (2.16) and later

LOADED_XCLBIN = "loaded.xclbin"
MIN_BO_BYTES = 8192 if PYNQ4 else 0

# What the simulated _xrt_download writes: an axlf magic and a marker, never a loadable image.
_XCLBIN_PLACEHOLDER = b"xclbin2\0cocotbpynq simulated PYNQ 4 _xrt_download\n"


def device_tree():
    """The directory standing for the simulated board's /proc/device-tree, or None for a configured board."""
    tree = os.environ.get("COCOTBPYNQ_DEVICE_TREE")
    return tree or None


def on_target():
    """``pynq.ps.ON_TARGET`` on the simulated board (always True for PYNQ 3, which has no such gate)."""
    if not PYNQ4:
        return True
    tree = device_tree()
    return tree is None or os.path.isfile(os.path.join(tree, "chosen", "pynq_board"))


def require_device(what):
    """Fail as PYNQ 4.0 does when host code first opens the device off target."""
    if not on_target():
        raise NameError(
            "name 'pyxrt' is not defined: PYNQ 4.0 imports pyxrt only on target "
            f"(pynq.ps.ON_TARGET), and the simulated device tree {device_tree()} has no "
            f"chosen/pynq_board; {what} cannot open the device")


def xrt_download():
    """The current-directory write of PYNQ 4.0's ``XrtDevice._xrt_download`` (nothing on PYNQ 3)."""
    if not PYNQ4:
        return None
    with open(LOADED_XCLBIN, "wb") as f:     # the real call opens it relative to the cwd, too
        f.write(_XCLBIN_PLACEHOLDER)
    return os.path.abspath(LOADED_XCLBIN)
