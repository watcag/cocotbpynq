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

"""AXI DMA (simple mode) as PYNQ's pynq.lib.dma.DMA sees it.

Each channel streams TDATA-wide beats (32, 64, 128, ... bits; the width is
read from the bus) from or into the buffer, and keeps the PG021 registers
PYNQ reads: DMACR, DMASR (Halted, Idle, DMAIntErr, IOC) and LENGTH.  Both
channels share one register file, ``channel._mmio``, at PYNQ's offsets (MM2S
at 0x00, S2MM at 0x30), so ``channel.idle``, ``channel.error``,
``channel.running`` and direct ``_mmio`` reads and writes behave as on the
board.  Each register access takes one clock, so a host polling loop advances
the simulation.

S2MM stops at TLAST or when the buffer length is reached; without TLAST by
then it flags DMAIntErr and halts (PG021 simple mode).  After completion the
S2MM LENGTH register holds the bytes actually written.  Writing DMACR.Reset
(bit 2) to either channel resets both: transfers in flight stop, the streams
are released and both channels are halted.
"""

import cocotb
import numpy as np
from .dut import CocotbPynqBusInterface
from cocotb.triggers import Event, RisingEdge, ReadOnly
from cocotb.task import resume

MAX_C_SG_LENGTH_WIDTH = 26
SR_HALTED, SR_IDLE, SR_INTERR, SR_IOC = 0x1, 0x2, 0x10, 0x1000


class DMA:
    def __init__(self, cp_businterfaces, axi_dma_el):
        cp_read_bus = None
        cp_write_bus = None

        # Discover read/write busses between axi_dma and DUT
        for bus_interface_el in axi_dma_el.findall("./BUSINTERFACES/BUSINTERFACE"):
            busname = bus_interface_el.get("BUSNAME")
            for cpbus_interface in cp_businterfaces.values():
                if(cpbus_interface.busname == busname):
                    if(bus_interface_el.get("VLNV").split(":")[:3] != ["xilinx.com","interface","axis"]):
                        raise AttributeError(f"non-AXI-Stream but between axi_dma and dut exists: {busname}")
                    if (bus_interface_el.get("TYPE") == "INITIATOR"):
                        cp_write_bus = cpbus_interface
                        if(cp_read_bus is not None): break
                    elif (bus_interface_el.get("TYPE") == "TARGET"):
                        cp_read_bus = cpbus_interface
                        if(cp_write_bus is not None): break

        width = MAX_C_SG_LENGTH_WIDTH
        for p in axi_dma_el.findall("./PARAMETERS/PARAMETER"):
            if p.get("NAME", "").lower() == "c_sg_length_width":
                width = int(p.get("VALUE"))
        self.buffer_max_size = (1 << width) - 1

        self.mmio = _Registers()
        if(cp_write_bus != None):
            self.sendchannel = DMA_Channel(cp_write_bus, "write", self.mmio, self.buffer_max_size)
        if(cp_read_bus != None):
            self.recvchannel = DMA_Channel(cp_read_bus, "read", self.mmio, self.buffer_max_size)


class _Registers:
    """Register file of one AXI DMA, shared by its channels (PYNQ's DMA.mmio)."""

    def __init__(self):
        self.channels = {}

    def _split(self, offset):
        base = 0x30 if offset >= 0x30 else 0x00
        if base not in self.channels:
            raise ValueError(f"no DMA channel at offset {offset:#x}")
        return self.channels[base], offset - base

    @resume
    async def read(self, offset=0, length=4):
        ch, reg = self._split(offset)
        await RisingEdge(ch.cpbus.cpdut.clk)
        if reg == 0x00:
            return ch.cr
        if reg == 0x04:
            return ch.sr
        if reg == 0x28:
            return ch.length
        return 0

    @resume
    async def write(self, offset, data):
        ch, reg = self._split(offset)
        await RisingEdge(ch.cpbus.cpdut.clk)
        if reg == 0x00:
            if data & 0x4:
                for c in self.channels.values():
                    c._reset()
            else:
                ch.cr = data
                if data & 0x1:
                    ch.sr &= ~SR_HALTED
                else:
                    ch._stop()
        elif reg == 0x04:
            ch.sr &= ~(data & 0x7000)          # write 1 to clear IOC/Dly/Err irq bits


class DMA_Channel():
    def __init__(self, cpbus: CocotbPynqBusInterface, direction: str, mmio=None, max_size=(1 << MAX_C_SG_LENGTH_WIDTH) - 1):
        if(direction not in ["read", "write"]):
            raise ValueError("direction must be \"read\" or \"write\"")
        self.direction = direction
        self.cpbus = cpbus
        self.beat_bytes = len(cpbus.TDATA) // 8
        self._mmio = mmio if mmio is not None else _Registers()
        self._offset = 0x00 if direction == "write" else 0x30
        self._mmio.channels[self._offset] = self
        self._max_size = max_size
        self._active_buffer = None
        self._first_transfer = True
        self._task = None
        self.cr = 0x1                          # PYNQ's DMA driver starts both channels
        self.sr = 0x0
        self.length = 0
        self.transferred = 0
        self.is_idle = Event()
        self.is_idle.set()
        if(self.direction == "write"):
            self.cpbus.TVALID.value = 0b0
        else:
            self.cpbus.TREADY.value = 0b0

    @property
    def running(self):
        return self._mmio.read(self._offset + 4) & 0x01 == 0x00

    @property
    def idle(self):
        return self._mmio.read(self._offset + 4) & 0x02 == 0x02

    @property
    def error(self):
        return self._mmio.read(self._offset + 4) & 0x70 != 0x0

    def start(self):
        self._mmio.write(self._offset, 0x0001)
        self._first_transfer = True

    def stop(self):
        self._mmio.write(self._offset, 0x0000)

    def transfer(self, array, start=0, nbytes=0):
        if self.sr & SR_HALTED:
            raise RuntimeError("DMA channel not started")
        if not (self.sr & SR_IDLE) and not self._first_transfer:
            raise RuntimeError("DMA channel not idle")
        if nbytes == 0:
            nbytes = array.nbytes - start
        if nbytes > self._max_size:
            raise ValueError(f"Transfer size is {nbytes} bytes, which exceeds the maximum DMA buffer size {self._max_size}.")
        if start % self.beat_bytes or nbytes % self.beat_bytes:
            raise MemoryError(f"Unaligned transfer: start and nbytes must be multiples of the {self.beat_bytes}-byte stream beat.")
        if self.direction == "write" and hasattr(array, "flush"):
            array.flush()
        mem = getattr(array, "_dram", None)
        if mem is None:
            mem = array
        mem = mem.reshape(-1).view("u1")[start:start + nbytes]
        self._active_buffer = array
        self._first_transfer = False
        self.sr &= ~(SR_IDLE | SR_INTERR | SR_IOC)
        self.length = nbytes
        self.is_idle.clear()
        stream = self.write_axi_stream if self.direction == "write" else self.read_axi_stream
        self._task = cocotb.start_soon(stream(mem))

    @resume
    async def wait(self):
        await self.is_idle.wait()
        if self.sr & SR_INTERR:
            raise RuntimeError("DMA Internal Error (transfer length 0?)")
        if self.direction == "read" and hasattr(self._active_buffer, "invalidate"):
            self._active_buffer.invalidate()
        self.transferred = self.length

    def _done(self, status):
        self.sr |= status
        self._task = None
        self.is_idle.set()

    def _stop(self):
        if self._task is not None:
            self._task.cancel()
        self._task = None
        if self.direction == "write":
            self.cpbus.TVALID.value = 0b0
        else:
            self.cpbus.TREADY.value = 0b0
        self.sr |= SR_HALTED
        self.is_idle.set()

    def _reset(self):
        self._stop()
        self.cr = 0x0
        self.sr = SR_HALTED
        self.length = 0

    async def write_axi_stream(self, mem):
        await self.cpbus.cpdut.await_reset()
        n = self.beat_bytes
        beats = len(mem) // n
        self.cpbus.TVALID.value = 0b1
        for i in range(beats):
            self.cpbus.TDATA.value = int.from_bytes(mem[i * n:(i + 1) * n].tobytes(), "little")
            self.cpbus.TLAST.value = 0b1 if (i == beats - 1) else 0b0
            await ReadOnly()
            while(self.cpbus.TREADY.value == 0b0):
                await RisingEdge(self.cpbus.cpdut.clk)
                await ReadOnly()
            await RisingEdge(self.cpbus.cpdut.clk)
        self.cpbus.TVALID.value = 0b0
        self._done(SR_IDLE | SR_IOC)

    async def read_axi_stream(self, mem):
        await self.cpbus.cpdut.await_reset()
        n = self.beat_bytes
        beats = len(mem) // n
        self.cpbus.TREADY.value = 0b1
        got = 0
        last = False
        while got < beats and not last:
            await ReadOnly()
            while(self.cpbus.TVALID.value == 0b0):
                await RisingEdge(self.cpbus.cpdut.clk)
                await ReadOnly()
            last = self.cpbus.TLAST.value == 0b1
            mem[got * n:(got + 1) * n] = np.frombuffer(int(self.cpbus.TDATA.value).to_bytes(n, "little"), "u1")
            got += 1
            await RisingEdge(self.cpbus.cpdut.clk)
        self.cpbus.TREADY.value = 0b0
        self.length = got * n
        if last:
            self._done(SR_IDLE | SR_IOC)
        else:
            self.sr |= SR_HALTED               # buffer full before TLAST
            self._done(SR_INTERR)
