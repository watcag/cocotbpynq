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

import cocotb
from .dut import CocotbPynqBusInterface, CocotbPynqDut
from cocotb.triggers import Event, RisingEdge, ReadOnly
import numpy as np
from threading import Lock
from cocotb.task import resume

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

        if(cp_write_bus != None):
            self.sendchannel = DMA_Channel(cp_write_bus, "write")
        if(cp_read_bus != None):
            self.recvchannel = DMA_Channel(cp_read_bus, "read")


class DMA_Channel():
    def __init__(self, cpbus: CocotbPynqBusInterface, direction: str):
        self.direction = direction
        self.cpbus = cpbus
        self.idle_lock = Lock()
        self.is_idle = Event()
        if(self.direction == "write"):
            self.cpbus.TVALID.value = 0b0
        else:
            self.cpbus.TREADY.value = 0b0
    @resume
    async def wait(self):
        await self.is_idle.wait()
        self.idle_lock.release()

    def transfer(self, array, start=0, nbytes=0):
        if start % 4:
            raise MemoryError("Unaligned transfer: start must be multiple of 4.")
        if nbytes % 4:
            raise MemoryError("Unaligned transfer: nbytes must be multiple of 4.")
        if nbytes == 0:
            nbytes = array.nbytes - start
        if(self.direction not in ["read", "write"]):
            raise ValueError("direction must be \"read\" or \"write\"")
        if(not self.idle_lock.acquire(False)):
            raise InterruptedError("DMA can not be accessed again until it has been waited")
        self.is_idle.clear()
        if (self.direction == "write"):
            cocotb.start_soon(self.write_axi_stream(np.frombuffer(array, np.uint32, nbytes>>2, start)))
        else:
            cocotb.start_soon(self.read_axi_stream(np.frombuffer(array, np.uint32, nbytes>>2, start)))
        # buf = np.frombuffer(data, np.uint32, num_words, 0)

    async def write_axi_stream(self, array: np.ndarray):
        await self.cpbus.cpdut.await_reset()
        self.cpbus.TVALID.value = 0b1
        for i in range(array.size):
            self.cpbus.TDATA.value = int(array.flat[i])
            self.cpbus.TLAST.value = 0b1 if (i == len(array) - 1) else 0b0
            await ReadOnly()
            x_ready = self.cpbus.TREADY.value
            while(x_ready == 0b0):
                await RisingEdge(self.cpbus.cpdut.clk)
                await ReadOnly()
                x_ready = self.cpbus.TREADY.value
            await RisingEdge(self.cpbus.cpdut.clk)
        self.cpbus.TVALID.value = 0b0
        self.is_idle.set()
    
    async def read_axi_stream(self, array: np.ndarray):
        await self.cpbus.cpdut.await_reset()
        max_num_words = array.size
        self.cpbus.TREADY.value = 0b1
        y_last = 0b0
        for i in range(max_num_words):
            await ReadOnly()
            y_valid = self.cpbus.TVALID.value
            while(y_valid == 0b0):
                await RisingEdge(self.cpbus.cpdut.clk)
                await ReadOnly()
                y_valid = self.cpbus.TVALID.value
            y_last = self.cpbus.TLAST.value
            array.flat[i] = (int(self.cpbus.TDATA.value))
            await RisingEdge(self.cpbus.cpdut.clk)
            if(y_last == 0b1):
                break
        self.cpbus.TREADY.value = 0b0
        self.is_idle.set()
    


