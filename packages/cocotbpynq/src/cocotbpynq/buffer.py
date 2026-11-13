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

import enum
import warnings

import numpy

from . import pynq_api

_next_address = 0x10000000


class xclBOSyncDirection(enum.IntEnum):
    """pyxrt.xclBOSyncDirection"""
    XCL_BO_SYNC_BO_TO_DEVICE = 0
    XCL_BO_SYNC_BO_FROM_DEVICE = 1


class bo:
    """pyxrt.bo of one allocation, with the sync overloads of the simulated board's pyxrt.

    ``sync(direction, size, offset)`` always; ``sync(direction)`` (the whole buffer object) only when
    ``pynq_api.PYXRT`` is XRT 2.16 or later.  Anything else raises pybind11's TypeError, as pyxrt does.
    """

    def __init__(self, allocation):
        self._allocation = allocation

    def size(self):
        return max(self._allocation.nbytes, pynq_api.MIN_BO_BYTES)

    def address(self):
        return self._allocation.physical_address

    def sync(self, *args):
        if len(args) == 1 and pynq_api.PYXRT_WHOLE_SYNC:
            direction, size, offset = args[0], self.size(), 0
        elif len(args) == 3:
            direction, size, offset = args
        else:
            overloads = "    1. (self: pyxrt.bo, arg0: pyxrt.xclBOSyncDirection, arg1: int, arg2: int) -> None\n"
            if pynq_api.PYXRT_WHOLE_SYNC:
                overloads += "    2. (self: pyxrt.bo, arg0: pyxrt.xclBOSyncDirection) -> None\n"
            raise TypeError("sync(): incompatible function arguments. The following argument types are "
                            f"supported:\n{overloads}\nInvoked with: <pyxrt.bo>, "
                            + ", ".join(map(repr, args)) + f" (simulated pyxrt of XRT {pynq_api.PYXRT})")
        direction = xclBOSyncDirection(direction)
        if offset < 0 or size < 0 or offset + size > self.size():
            raise RuntimeError(f"bo sync of {size} bytes at {offset} outside the {self.size()}-byte buffer object")
        self._allocation._copy(direction is xclBOSyncDirection.XCL_BO_SYNC_BO_TO_DEVICE, offset, size)


class EmbeddedDevice:
    """The calls of PYNQ's EmbeddedDevice that a PynqBuffer makes (flush, invalidate)."""
    name = "embedded_xrt0"

    def flush(self, bo, offset, ptr, size):
        if not pynq_api.PYNQ4:                      # PYNQ 3.0.1: xclSyncBO(handle, bo, dir, size, offset)
            return bo.sync(xclBOSyncDirection.XCL_BO_SYNC_BO_TO_DEVICE, size, offset)
        try:                                        # PYNQ 4.0.0 pl_server/xrt_device.py: XrtDevice.flush
            bo.sync(xclBOSyncDirection.XCL_BO_SYNC_BO_TO_DEVICE)
        except Exception as e:
            raise RuntimeError(f"Buffer Flush Failed: {str(e)}")

    def invalidate(self, bo, offset, ptr, size):
        if not pynq_api.PYNQ4:
            return bo.sync(xclBOSyncDirection.XCL_BO_SYNC_BO_FROM_DEVICE, size, offset)
        try:
            bo.sync(xclBOSyncDirection.XCL_BO_SYNC_BO_FROM_DEVICE)
        except Exception as e:
            raise RuntimeError(f"Buffer Invalidate Failed: {str(e)}")


DEVICE = EmbeddedDevice()


class PynqBuffer(numpy.ndarray):
    """pynq.buffer.PynqBuffer in simulation, with a write-back cache model.

    The array is what the CPU sees; ``_dram`` is DRAM as the DMA sees it.
    For a cacheable buffer, ``flush()`` writes the CPU view to DRAM and
    ``invalidate()`` reloads it from DRAM, so a host that skips either sees
    stale data as it would on the board.  A non-cacheable buffer is one array.

    A slice is a view of its allocation, as in PYNQ: it keeps the allocation's
    physical address plus its byte offset.  Syncing a slice syncs its byte range
    on PYNQ 3 and the whole allocation on PYNQ 4 (``bo.sync`` takes no range), so
    an ``invalidate()`` of one slice also drops unflushed CPU writes elsewhere in
    the buffer.  On PYNQ 4 the sync goes through ``bo.sync(direction)``, which the
    simulated board's pyxrt may lack (``pynq_api.PYXRT``): then it raises as there.  After ``freebuffer()`` the allocation is unmapped: syncing it, or
    handing it to a DMA, raises.
    """

    def __array_finalize__(self, obj):
        self._dram = None                     # views and copies are plain CPU memory
        self._root = None
        self._offset = 0
        self.cacheable = False
        self.physical_address = 0
        root = getattr(obj, "_root", None)
        if root is None and getattr(obj, "_dram", None) is not None:
            root = obj
        if root is not None and isinstance(obj, PynqBuffer):
            offset = self.__array_interface__["data"][0] - root.__array_interface__["data"][0]
            if 0 <= offset < max(root.nbytes, 1):    # a view into the allocation, not a computed copy
                self._root, self._offset = root, offset
                self.cacheable = root.cacheable
                self.physical_address = root.physical_address + offset

    @property
    def device_address(self):
        return self.physical_address

    def _allocation(self):
        root = self._root if self._root is not None else (self if self._dram is not None else None)
        if root is not None and root._freed:
            raise RuntimeError("buffer used after freebuffer(): PYNQ unmapped it")
        return root

    @property
    def bo(self):
        root = self._root if self._root is not None else self
        return root.__dict__.get("_bo")

    @property
    def device(self):
        return DEVICE if self.bo is not None else None

    @property
    def offset(self):
        return self._offset

    @property
    def virtual_address(self):
        return self.__array_interface__["data"][0]

    def _copy(self, to_device, offset, size):
        """Move bytes [offset, offset + size) of this allocation between the CPU view and DRAM."""
        if self._dram is self:
            return
        window = slice(offset, offset + size)
        cpu = self.reshape(-1).view("u1")
        dram = self._dram.reshape(-1).view("u1")
        if to_device:
            dram[window] = cpu[window]
        else:
            cpu[window] = dram[window]

    def flush(self):
        """PynqBuffer.flush: ``device.flush(bo, offset, virtual_address, nbytes)``."""
        root = self._allocation()
        if root is not None:
            DEVICE.flush(root._bo, self._offset, self.virtual_address, self.nbytes)

    def invalidate(self):
        root = self._allocation()
        if root is not None:
            DEVICE.invalidate(root._bo, self._offset, self.virtual_address, self.nbytes)

    def sync_to_device(self):
        self.flush()

    def sync_from_device(self):
        self.invalidate()

    def _dma_memory(self, start, nbytes):
        """The bytes a DMA reads or writes: DRAM at this buffer's physical address."""
        root = self._allocation()
        if root is None:
            return self.reshape(-1).view("u1")[start:start + nbytes]
        base = self._offset + start
        return root._dram.reshape(-1).view("u1")[base:base + nbytes]

    def freebuffer(self):
        root = self._root if self._root is not None else self
        if root._dram is not None:
            root._freed = True

    def close(self):
        warnings.warn(".close no longer functional - use scopes to manage buffers", DeprecationWarning)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.freebuffer()
        return False


def allocate(shape, dtype="u4", target=None, cacheable=True, **kwargs):
    global _next_address
    pynq_api.require_device("pynq.allocate")
    buf = numpy.zeros(shape, dtype=dtype).view(PynqBuffer)
    buf.cacheable = cacheable
    buf._dram = numpy.zeros(shape, dtype=dtype) if cacheable else buf
    buf._freed = False
    buf.physical_address = _next_address
    buf._bo = bo(buf)
    _next_address += (max(buf.nbytes, pynq_api.MIN_BO_BYTES) + 0xFFF) & ~0xFFF
    return buf
