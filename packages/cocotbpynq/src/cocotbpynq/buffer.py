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

import warnings

import numpy

from . import pynq_api

_next_address = 0x10000000


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
    the buffer.  After ``freebuffer()`` the allocation is unmapped: syncing it, or
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

    def _sync(self, to_device):
        root = self._allocation()
        if root is None or root._dram is root:
            return
        cpu = root.reshape(-1).view("u1")
        dram = root._dram.reshape(-1).view("u1")
        if pynq_api.PYNQ4 or self is root:
            window = slice(None)
        else:
            window = slice(self._offset, self._offset + self.nbytes)
        if to_device:
            dram[window] = cpu[window]
        else:
            cpu[window] = dram[window]

    def flush(self):
        self._sync(True)

    def invalidate(self):
        self._sync(False)

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
    _next_address += (max(buf.nbytes, pynq_api.MIN_BO_BYTES) + 0xFFF) & ~0xFFF
    return buf
