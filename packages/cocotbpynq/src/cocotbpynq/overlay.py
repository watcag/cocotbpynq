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

from .dma import DMA
from .dut import CocotbPynqDut
import cocotb
import os
from xml.etree import ElementTree

hwh_tree: ElementTree.Element = None
cptop: CocotbPynqDut = None

class DefaultIP:
    """ Currently just used to allow recursive hierarchical reference"""
    pass

class HierarchyObject:
    """
    Hierarchy object used by overlay class to hierarchically reference IPs

    Parameters
    ----------
    hierarchy : str/dict
        IP names or hierarchy of IP names
    """
    def __init__(self, hierarchy):
        self.hierarchy_dict = {}
        for hierarchy_object in hierarchy.keys():
            if(type(hierarchy[hierarchy_object]) == str):
                self.hierarchy_dict[hierarchy_object] = self.create_IP(hierarchy[hierarchy_object])
            else:
                self.hierarchy_dict[hierarchy_object] = HierarchyObject(hierarchy[hierarchy_object])

    def create_IP(self, instance_name):
        """
        Add an IP object to the hierarchy

        Parameters
        ----------
        hierarchy : str/dict
            IP instance type
        """
        instance_el = hwh_tree.find(f"./MODULES/MODULE[@INSTANCE='{instance_name}']")
        
        # Currently only DMA is supported here. Add more cases for more IP blocks as needed
        if(instance_el.get("VLNV").split(":")[:3] == ["xilinx.com", "ip", "axi_dma"]):
            return DMA(cptop.bus_interfaces, instance_el)
        else:
            return DefaultIP()

    def __getattr__(self, key):
        return self.hierarchy_dict[key]


class Overlay(HierarchyObject):
    """
    Drop in replacement for PYNQ overlay class

    Parameters
    ----------
    bitfile_name : str
        Name of bitstream file. Used to determine hwh file with same name. Needed for parity with PYNQ
    """
    def __init__(self, bitfile_name=None):
        bitstream_dir = os.getenv("HWH_LOCATION_DIR")
        if(not bitstream_dir):
            raise EnvironmentError("No HWH_LOCATION_DIR environment variable found")
        bitstream_path = os.path.abspath(os.path.join(bitstream_dir, bitfile_name))
        hwh_name = os.path.splitext(bitstream_path)[0] + ".hwh"
        if(not os.path.isfile(hwh_name)):
            raise ValueError(f"HWH file does not exist at {hwh_name}")

        # Create global variable hwh_tree
        global hwh_tree
        hwh_tree = ElementTree.parse(hwh_name).getroot()

        # Auto-detect PR mode: if PR_CTRL_SHM is set, the cocotb DUT is the
        # pr_cocotb_top wrapper, not the user's module directly.
        pr_mode = os.environ.get('PR_CTRL_SHM') is not None
        if pr_mode:
            dut_module_name = 'pr_cocotb_top'
        else:
            dut_module_name = cocotb.top._name
        dut_module_el = hwh_tree.find(f"./MODULES/MODULE[@MODTYPE='{dut_module_name}']")

        # Create global variable cptop
        global cptop
        cptop = CocotbPynqDut(cocotb.top, dut_module_el, True, skip_modtype_check=pr_mode)

        # discover all hierarchichally referenceble instances, as per how pynq library discovers them (for Zynq)
        processing_system_el = hwh_tree.find(f"./MODULES/MODULE[@MODTYPE='processing_system7']")
        if (processing_system_el is None):
            raise RuntimeError("No processing_system7 found. Please check that the HWH file you have generated is for a Zynq device. Only Zynq devices are supported at this time")
        instances_to_add = []
        for memrange in processing_system_el.findall("./MEMORYMAP/MEMRANGE"):
            instances_to_add.append(memrange.get("INSTANCE"))

        # Create pre-processor dict hierarchy
        hierarchy_to_add = {}
        for instance_name in instances_to_add:
            instance_el = hwh_tree.find(f"./MODULES/MODULE[@INSTANCE='{instance_name}']")
            instance_fullname = instance_el.get("FULLNAME")
            instance_hierarchy = instance_fullname.lstrip("/").split("/")
            imm_hierarchy = hierarchy_to_add
            for next_hierarchy_item in instance_hierarchy:
                if(next_hierarchy_item not in imm_hierarchy):
                    imm_hierarchy[next_hierarchy_item] = {}
                    if(next_hierarchy_item == instance_hierarchy[-1]):
                        imm_hierarchy[next_hierarchy_item] = instance_name
                imm_hierarchy = imm_hierarchy[next_hierarchy_item]

        # Create actual referenceable hierarchy structure recursively
        super().__init__(hierarchy_to_add)

    def pr_download(self, partial_region, partial_bit, dtbo=None, program=True, icap=False):
        """Download a partial bitstream onto PL.

        Matches the pynq.Overlay.pr_download() API. In simulation, the
        partial_bit name is used to identify which RM variant to load
        (the .bit/.bin extension is stripped if present).

        Parameters
        ----------
        partial_region : str
            Name of the hierarchical block / partition to reconfigure.
        partial_bit : str
            Name of the partial bitstream (or RM variant name).
        dtbo : str
            Ignored in simulation.
        program : bool
            Ignored in simulation.
        icap : bool
            Ignored in simulation (no distinction between PCAP/ICAP in sim).
        """
        from cocotb.task import resume
        from cocotb.triggers import RisingEdge
        from .pr.cocotb_mode import pr_reconfigure

        # Strip .bit/.bin extension if present
        rm_name = partial_bit
        for ext in ('.bit', '.bin'):
            if rm_name.endswith(ext):
                rm_name = rm_name[:-len(ext)]
                break

        # Post-reconfigure settle cycles. The framework's DPI barrier needs
        # a non-zero number of clock cycles after reconfig to ensure the new
        # RM is fully synchronised with the static region before the test
        # issues its first MMIO/DMA operation. The historical default was 4
        # cycles (chosen empirically). PR_RECONFIG_SETTLE_CYCLES env var
        # exposes this so benchmarks can isolate framework overhead from
        # mechanism cost; 1 is the minimum that keeps the existing examples
        # functional in our regression set.
        settle = int(os.environ.get('PR_RECONFIG_SETTLE_CYCLES', '1'))
        from ._pr_engine import trace

        @resume
        async def _do_reconfig():
            with trace.span('overlay.pr_download',
                            partition=partial_region, rm=rm_name,
                            settle_cycles=settle):
                await pr_reconfigure(partial_region, rm_name)
                if cptop is not None and settle > 0:
                    for _ in range(settle):
                        await RisingEdge(cptop.clk)

        _do_reconfig()

    def chain(self, partition_names):
        """Route partitions in a pipeline via AXI-Stream switch.

        Matches pynq-pr's Overlay.chain() API. Programs the switch so
        data flows: DMA₀ → partition[0] → partition[1] → … → DMA₀.

        Parameters
        ----------
        partition_names : list of str
            Ordered list of partition names to chain.

        Returns
        -------
        DMA
            The first partition's DMA object (send + recv channels).
        """
        import json
        from .mmio import MMIO

        partition_map_str = os.environ.get('PR_PARTITION_MAP')
        switch_addr_str = os.environ.get('PR_SWITCH_ADDR')
        if partition_map_str is None or switch_addr_str is None:
            raise RuntimeError(
                "chain() requires PR_PARTITION_MAP and PR_SWITCH_ADDR env vars "
                "(set automatically by PRCocotbRunner when axis_switch is configured)"
            )

        partition_map = json.loads(partition_map_str)
        switch_addr = int(switch_addr_str, 0)
        switch_range = int(os.environ.get('PR_SWITCH_RANGE', '0x10000'), 0)
        num_ports = int(os.environ.get('PR_NUM_SWITCH_PORTS', str(2 * len(partition_map))))

        sw = MMIO(switch_addr, switch_range)
        indices = [partition_map[n] for n in partition_names]

        # Build routing: first RP ← its DMA, middle RPs chained, last RP → first DMA
        mapping = {}
        mapping[2 * indices[0]] = 2 * indices[0] + 1
        for k in range(len(indices) - 1):
            mapping[2 * indices[k + 1]] = 2 * indices[k]
        mapping[2 * indices[0] + 1] = 2 * indices[-1]

        # Program switch
        DISABLE = 0x80000000
        for mi in range(num_ports):
            sw.write(0x40 + 4 * mi, mapping.get(mi, DISABLE))
        sw.write(0x00, 0x2)  # commit

        # Return first partition's DMA
        first_dma_name = os.environ.get(f'PR_DMA_{partition_names[0]}')
        if first_dma_name:
            return getattr(self, first_dma_name)
        # Fallback: return axi_dma_0 (first partition's DMA by convention)
        return self.axi_dma_0
