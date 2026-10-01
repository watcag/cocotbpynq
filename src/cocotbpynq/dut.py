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
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Event
from cocotb.utils import get_sim_time as gst
from xml.etree import ElementTree
from cocotb.handle import SimHandleBase

class CocotbPynqDut:
    def __init__(self, dut: SimHandleBase, dut_module_el, reset_on_init=True, skip_modtype_check=False):
        self.dut = dut
        dut_module_name, hwh_module_type = cocotb.top._name, dut_module_el.get("MODTYPE")
        if(not skip_modtype_check and dut_module_name != hwh_module_type):
            raise ValueError("Given module is not the same module type as dut")
        self.bus_interfaces = {}
        for bus_interface_el in dut_module_el.findall("./BUSINTERFACES/BUSINTERFACE"):
            cpbus = CocotbPynqBusInterface(self, bus_interface_el)
            self.bus_interfaces[cpbus.portname] = cpbus
        # Create Synchronization event to avoid changing signals in reset state
        self.done_reset = Event() 
        self.done_reset.clear()

        # Automatically find dut clk/reset names and reset polarity from HWH
        clk_el = dut_module_el.find("./PORTS/PORT[@SIGIS='clk']")
        rst_el = dut_module_el.find("./PORTS/PORT[@SIGIS='rst']")
        self.clk = getattr(self.dut, clk_el.get("NAME"))
        self.rst = getattr(self.dut, rst_el.get("NAME"))
        self.rst_active_low = (rst_el.get("POLARITY") == "ACTIVE_LOW")
        # Start common signals
        cocotb.start_soon(Clock(self.clk, 1000, 'step').start())
        if(reset_on_init):
            # Reset dut for 3 cycles, then wait 1 cycle before allowing anyone to touch dut
            cocotb.start_soon(self.reset_dut(3, 1))

        self.instance_name = dut_module_el.get("INSTANCE")

    async def reset_dut(self, reset_cycles: int, waiting_cycles: int):
        self.done_reset.clear()
        self.rst.value = not self.rst_active_low
        await ClockCycles(self.dut.clk, reset_cycles)
        self.rst.value = self.rst_active_low
        self.rst._log.info("Reset complete")
        await ClockCycles(self.clk, waiting_cycles)
        self.done_reset.set()

    async def await_reset(self):
        if (self.done_reset.is_set()):
            return
        self.rst._log.info("MMIO awaiting device reset")
        time = gst('step')
        await self.done_reset.wait()
        time2 = gst('step')
        self.rst._log.info(f"Waited {time2-time} timesteps for DUT reset")
        return
    
class CocotbPynqBusInterface:
    """
        Bus Interface object derived from HWH file meant to control bus interfaces
        directly attached to a cocotb device
    """    

    def __init__(self, cpdut, bus_interface_el: ElementTree.Element):
        """_summary_

        Args:
            cpdut (_type_): _description_
            bus_int_el (ElementTree.Element): _description_
        """        
        self.cpdut = cpdut
        self.busname = bus_interface_el.get("BUSNAME")
        self.portname = bus_interface_el.get("NAME")
        for portmap in bus_interface_el.findall("./PORTMAPS/PORTMAP"):
            self.__setattr__(portmap.get("LOGICAL"), cpdut.dut.__getattr__(portmap.get("PHYSICAL")))