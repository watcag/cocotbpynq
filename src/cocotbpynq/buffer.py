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

import os

import numpy

from .axi_mem import device_memory

_next_address = 0x10000000
# "pynq": a non-cacheable buffer is one array (host and device writes visible at once), as on the board;
# "strict": every buffer keeps a separate device view, so a missing flush / invalidate shows even for
# non-cacheable buffers (set_cache_model or COCOTBPYNQ_CACHE)
_cache_model = os.environ.get("COCOTBPYNQ_CACHE", "pynq")


def set_cache_model(model: str):
    global _cache_model
    if model not in ("pynq", "strict"):
        raise ValueError("cache model is 'pynq' or 'strict'")
    _cache_model = model


class PynqBuffer(numpy.ndarray):
    """pynq.buffer.PynqBuffer in simulation, with a write-back cache model.

    The array is what the CPU sees; ``_dram`` is DRAM as the DMA and the PL
    masters (cocotbpynq.axi_mem) see it.  For a cacheable buffer, ``flush()``
    writes the CPU view to DRAM and ``invalidate()`` reloads it from DRAM, so a
    host that skips either sees stale data as it would on the board.  A
    non-cacheable buffer is one array (unless the cache model is "strict").
    """

    def __array_finalize__(self, obj):
        self._dram = None                     # views and copies are plain CPU memory
        self.cacheable = False
        self.physical_address = 0

    @property
    def device_address(self):
        return self.physical_address

    def flush(self):
        if self._dram is not None and self._dram is not self:
            self._dram[...] = self

    def invalidate(self):
        if self._dram is not None and self._dram is not self:
            self[...] = self._dram

    def sync_to_device(self):
        self.flush()

    def sync_from_device(self):
        self.invalidate()

    def unflushed_bytes(self) -> int:
        """Bytes whose CPU view differs from the device view (host writes not yet flushed, or device writes
        not yet invalidated)."""
        if self._dram is None or self._dram is self:
            return 0
        a = numpy.asarray(self).reshape(-1).view(numpy.uint8)
        return int(numpy.count_nonzero(a != numpy.asarray(self._dram).reshape(-1).view(numpy.uint8)))

    def freebuffer(self):
        if self._dram is not None:
            device_memory.remove(self.physical_address)

    def close(self):
        self.freebuffer()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.freebuffer()
        return False


def allocate(shape, dtype="u4", target=None, cacheable=True, **kwargs):
    global _next_address
    buf = numpy.zeros(shape, dtype=dtype).view(PynqBuffer)
    buf.cacheable = cacheable
    split = cacheable or _cache_model == "strict"
    buf._dram = numpy.zeros(shape, dtype=dtype) if split else buf
    buf.physical_address = _next_address
    _next_address += (buf.nbytes + 0xFFF) & ~0xFFF
    device_memory.add(buf.physical_address, numpy.asarray(buf._dram), numpy.asarray(buf))
    return buf
