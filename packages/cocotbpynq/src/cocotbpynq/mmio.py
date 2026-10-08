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
from .dut import CocotbPynqDut
import numpy as np
from cocotb.triggers import RisingEdge, ReadOnly
from cocotb.task import resume

class MMIO():
    """
    Drop in replacement for Pynq MMIO class.
    Finds hwh_tree(associated with most recent overlay creation), and
    finds the correct MMIO port  in a design based on inputted base_addr
    and length

    Parameters
    ----------
    base_addr : int
        The base address of the MMIO's address range
    length : int
        Size of MMIO's address range
    """
    def __init__(self, base_addr, length=4):
        from .overlay import hwh_tree, cptop
        self.base_addr = base_addr
        self.length = length # Number of accessible bytes
        self.cpdut: CocotbPynqDut = cptop
        processing_system_el = hwh_tree.find("./MODULES/MODULE[@MODTYPE='processing_system7']")
        if (processing_system_el is None):
            raise RuntimeError("No processing_system7 found. Please check that the HWH file you have generated is for a Zynq device. Only Zynq devices are supported at this time")
        mmio_memrange_el = None
        for memrange_el in processing_system_el.findall("./MEMORYMAP/MEMRANGE"):
            if(memrange_el.get("INSTANCE") != self.cpdut.instance_name):
                continue
            if(int(memrange_el.get("BASEVALUE"),16) > base_addr) | (int(memrange_el.get("HIGHVALUE"),16) < base_addr+length):
                continue
            mmio_memrange_el = memrange_el
        if(mmio_memrange_el == None):
            raise RuntimeError("No MMIO block found attached to DUT for that memory range")
        mmio_bus_interface_name = mmio_memrange_el.get("SLAVEBUSINTERFACE")
        self.cpbus = self.cpdut.bus_interfaces[mmio_bus_interface_name]
        self.cpbus.ARVALID.value = 0b0
        self.cpbus.AWVALID.value = 0b0
        self.cpbus.BREADY.value = 0b0
        self.cpbus.RREADY.value = 0b0
        self.cpbus.WVALID.value = 0b0

    @resume
    async def read(self, offset=0, length=4, word_order="little"):
        """The method to read data from MMIO.

        For the `word_order` parameter, it is only effective when
        operating 8 bytes. If it is `little`, from MSB to LSB, the
        bytes will be offset+4, offset+5, offset+6, offset+7, offset+0,
        offset+1, offset+2, offset+3. If it is `big`, from MSB to LSB,
        the bytes will be offset+0, offset+1, ..., offset+7.
        This is different than the byte order (endianness); notice
        the endianness has not changed.
        
        NOTE: This function is heavily inspired by the PYNQ MMIO read function
        for the sake of parity, but must be copied to cocotbpynq to remove
        any PYNQ dependency(which would prevent this from running on
        normal systems). 

        Parameters
        ----------
        offset : int
            The read offset from the MMIO base address.
        length : int
            The length of the data in bytes.
        word_order : str
            The word order of the 8-byte reads.

        Returns
        -------
        list
            A list of data read out from MMIO

        """
        await self.cpdut.await_reset()
        if length not in [1, 2, 4, 8]:
            raise ValueError(
                "MMIO currently only supports " "1, 2, 4 and 8-byte reads."
            )
        if offset < 0:
            raise ValueError("Offset cannot be negative.")
        if length == 8 and word_order not in ["big", "little"]:
            raise ValueError("MMIO only supports big and little endian.")
        if offset % 4:
            raise MemoryError("Unaligned read: offset must be multiple of 4.")

        # Read data out
        lsb = int(await self.single_read_axi_lite(offset))
        if length == 8:
            if word_order == "little":
                return ((int(await self.single_read_axi_lite(offset + 4))) << 32) + lsb
            else:
                return (lsb << 32) + int(await self.single_read_axi_lite(offset + 4))
        else:
            return lsb & ((2 ** (8 * length)) - 1)   

    @resume
    async def write(self, offset, data):
        """The method to write data to MMIO.

        NOTE: This function is heavily inspired by the PYNQ MMIO read function
        for the sake of parity, but must be copied to cocotbpynq to remove
        any PYNQ dependency(which would prevent this from running on
        normal systems). 
        Parameters
        ----------
        offset : int
            The write offset from the MMIO base address.
        data : int / bytes
            The integer(s) to be written into MMIO.

        Returns
        -------
        None

        """
        await self.cpdut.await_reset()
        if offset < 0:
            raise ValueError("Offset cannot be negative.")

        if offset % 4:
            raise MemoryError("Unaligned write: offset must be multiple of 4.")

        if type(data) is int:
            await self.single_write_axi_lite(offset, data)
        elif type(data) is bytes:
            length = len(data)
            num_words = length >> 2
            if length % 4:
                raise MemoryError("Unaligned write: data length must be multiple of 4.")
            buf = np.frombuffer(data, np.uint32, num_words, 0)
            for i in range(len(buf)):
                await self.single_write_axi_lite(offset + 4*i, data)
        else:
            raise ValueError("Data type must be int or bytes.")
        
    async def single_write_axi_lite(self, offset, data):
        """The method to carry out AXI Lite write transaction at cocotb level.

        Parameters
        ----------
        offset : int
            The write offset from the MMIO base address.
        data : int / bytes
            The integer(s) to be written into MMIO.

        Returns
        -------
        None

        """
        # Address and data together: an AXI master must not wait for AWREADY
        # before asserting WVALID, and a slave may wait for both valids.
        self.cpbus.AWADDR.value = offset
        self.cpbus.AWVALID.value = 0b1
        self.cpbus.WDATA.value = data
        self.cpbus.WSTRB.value = 0xF
        self.cpbus.WVALID.value = 0b1
        aw_done = w_done = False
        while not (aw_done and w_done):
            await ReadOnly()
            aw_fire = not aw_done and self.cpbus.AWREADY.value == 0b1
            w_fire = not w_done and self.cpbus.WREADY.value == 0b1
            await RisingEdge(self.cpdut.clk)
            if aw_fire:
                aw_done = True
                self.cpbus.AWVALID.value = 0b0
            if w_fire:
                w_done = True
                self.cpbus.WVALID.value = 0b0
                self.cpbus.WSTRB.value = 0x0

        # Accept response back
        self.cpbus.BREADY.value = 0b1
        await ReadOnly()
        periph_resp_valid = self.cpbus.BVALID.value
        while(periph_resp_valid == 0b0):
            await RisingEdge(self.cpdut.clk)
            await ReadOnly()
            periph_resp_valid = self.cpbus.BVALID.value
        write_resp = self.cpbus.BRESP.value
        await RisingEdge(self.cpdut.clk)
        self.cpbus.BREADY.value = 0b0
        if (write_resp != 0b00):
            print(f"Write Error occured. Response: {bin(write_resp)}")

    async def single_read_axi_lite(self, offset):
        """The method to carry out AXI Lite read transaction at cocotb level.

        Parameters
        ----------
        offset : int
            The write offset from the MMIO base address.

        Returns
        -------
        int : Value read from base address + given offset

        """
        # Assert address
        self.cpbus.ARADDR.value = offset
        self.cpbus.ARVALID.value = 0b1
        await ReadOnly()
        periph_addr_ready = self.cpbus.ARREADY.value
        while(periph_addr_ready == 0b0):
            await RisingEdge(self.cpdut.clk)
            await ReadOnly()
            periph_addr_ready = self.cpbus.ARREADY.value
        await RisingEdge(self.cpdut.clk)
        self.cpbus.ARVALID.value = 0b0

        # Accept value back
        self.cpbus.RREADY.value = 0b1
        await ReadOnly()
        periph_data_valid = self.cpbus.RVALID.value
        while(periph_data_valid == 0b0):
            await RisingEdge(self.cpdut.clk)
            await ReadOnly()
            periph_data_valid = self.cpbus.RVALID.value
        read_data = int(self.cpbus.RDATA.value)
        read_resp = self.cpbus.RRESP.value
        await RisingEdge(self.cpdut.clk)
        self.cpbus.RREADY.value = 0b0
        if (read_resp != 0b00):
            print(f"Read Error occured: {bin(read_resp)}")
        return read_data