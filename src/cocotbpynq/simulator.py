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

from cocotb import test
from cocotb.task import bridge
from os import environ
if("COCOTB_SYS_ARGV" in environ):
    argv=environ["COCOTB_SYS_ARGV"].split()
else:
    argv=None

def synctest(test_func):
    """Wrap synchronous test function as async function so that it can synchronously call
    cocotb.continue decorated functions (like MMIO read/write or DMA wait), such that 
    test_func will block until that call is complete(like await).

    The purpose of this is so that a function that is used to interface with a Pynq board
    can also be used exactly as is for simulation with cocotbpynq library, only requiring to
    be wrapped with cocotbpynq.synctest when used for simulation"""
    qualname = test_func.__qualname__
    module = test_func.__module__
    test_func = bridge(test_func)
    async def async_test_func(dut):
        await test_func(dut)
    cocotbtest = test(async_test_func)

    # Ensure test result output is same as if you just decorated main with cocotb.test
    cocotbtest.__module__ = module
    cocotbtest.__qualname__ = qualname
    return cocotbtest