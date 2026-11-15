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

import numpy

_next_address = 0x10000000


class PynqBuffer(numpy.ndarray):
    """pynq.buffer.PynqBuffer in simulation, with a write-back cache model.

    The array is what the CPU sees; ``_dram`` is DRAM as the DMA sees it.
    For a cacheable buffer, ``flush()`` writes the CPU view to DRAM and
    ``invalidate()`` reloads it from DRAM, so a host that skips either sees
    stale data as it would on the board.  A non-cacheable buffer is one array.
    """

    def __array_finalize__(self, obj):
        self._dram = None                     # views and copies are plain CPU memory
        self.cacheable = False
        self.physical_address = 0

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

    def freebuffer(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def allocate(shape, dtype="u4", target=None, cacheable=True, **kwargs):
    global _next_address
    buf = numpy.zeros(shape, dtype=dtype).view(PynqBuffer)
    buf.cacheable = cacheable
    buf._dram = numpy.zeros(shape, dtype=dtype) if cacheable else buf
    buf.physical_address = _next_address
    _next_address += (buf.nbytes + 0xFFF) & ~0xFFF
    return buf
