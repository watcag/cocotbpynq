# cocotbpynq - a cocotb based emulation tool for PYNQ-targetting code
# Copyright (C) 2026 WatCAG, University of Waterloo
# SPDX-License-Identifier: GPL-3.0-or-later

"""The part of pyxrt a PynqBuffer exposes (``buf.bo``), as the simulated board's pyxrt binds it.

Host code that works around a board's pyxrt (e.g. ``buf.bo.sync(direction, buf.bo.size(), 0)`` where
``sync(direction)`` is missing) runs the same way against ``cocotbpynq.pyxrt``.
"""

from .buffer import bo, xclBOSyncDirection  # noqa: F401
