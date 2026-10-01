"""
Simulation overlay for pynq-pr.

This wraps cocotbpynq's low-level overlay/MMIO APIs behind the same
high-level routing helpers that users see on hardware.
"""

import json
import os

from cocotbpynq import MMIO, Overlay as _CocotbOverlay, allocate
from cocotbpynq import overlay as _cocotb_overlay


class AxisSwitch:
    """AXI4-Stream switch controller backed by cocotbpynq.MMIO."""

    _CTRL_REG = 0x00
    _MI_MUX_BASE = 0x40
    _COMMIT = 0x2
    _DISABLE = 0x80000000

    def __init__(self, base_addr, addr_range, num_ports):
        self._mmio = MMIO(base_addr, addr_range)
        self.num_ports = num_ports

    def route(self, mapping):
        for mi in range(self.num_ports):
            si = mapping.get(mi, self._DISABLE)
            self._mmio.write(self._MI_MUX_BASE + 4 * mi, si)
        self._mmio.write(self._CTRL_REG, self._COMMIT)

    def default(self):
        mapping = {}
        for i in range(self.num_ports // 2):
            mapping[2 * i] = 2 * i + 1
            mapping[2 * i + 1] = 2 * i
        self.route(mapping)


class Overlay(_CocotbOverlay):
    """pynq-pr style simulation overlay."""

    def __init__(self, bitfile_name=None, download=True, **kwargs):
        super().__init__(bitfile_name)
        partition_map_str = os.environ.get("PR_PARTITION_MAP")
        self._partitions = json.loads(partition_map_str) if partition_map_str else {}
        self.ip_dict = self._build_ip_dict()

        self._switch = None
        switch_addr_str = os.environ.get("PR_SWITCH_ADDR")
        if switch_addr_str is not None:
            switch_addr = int(switch_addr_str, 0)
            switch_range = int(os.environ.get("PR_SWITCH_RANGE", "0x10000"), 0)
            num_ports = int(
                os.environ.get(
                    "PR_NUM_SWITCH_PORTS",
                    str(2 * len(self._partitions)),
                )
            )
            self._switch = AxisSwitch(switch_addr, switch_range, num_ports)
            self._switch.default()

    def _build_ip_dict(self):
        """Build the small subset of PYNQ's ip_dict used by pynq-pr tests."""
        ip_dict = {}
        hwh_tree = getattr(_cocotb_overlay, "hwh_tree", None)
        if hwh_tree is None:
            return ip_dict

        processing_system_el = hwh_tree.find("./MODULES/MODULE[@MODTYPE='processing_system7']")
        if processing_system_el is None:
            return ip_dict

        for memrange in processing_system_el.findall("./MEMORYMAP/MEMRANGE"):
            bus_name = memrange.get("SLAVEBUSINTERFACE")
            if not bus_name:
                continue

            base = int(memrange.get("BASEVALUE"), 16)
            high = int(memrange.get("HIGHVALUE"), 16)
            info = {
                "phys_addr": base,
                "addr_range": high - base,
            }
            ip_dict[bus_name] = info

            if bus_name.endswith("_ctrl"):
                partition_name = bus_name[:-len("_ctrl")]
                if partition_name in self._partitions:
                    ip_dict[f"{partition_name}/rp/ctrl"] = info

        return ip_dict

    def _resolve_hierarchy_path(self, path):
        obj = self
        for part in path.split("/"):
            obj = getattr(obj, part)
        return obj

    def _resolve_dma(self, partition_name):
        part = getattr(self, partition_name, None)
        if part is not None and hasattr(part, "dma"):
            return part.dma

        dma_name = os.environ.get(f"PR_DMA_{partition_name}")
        if dma_name:
            return self._resolve_hierarchy_path(dma_name)

        if hasattr(self, "axi_dma_0"):
            return self.axi_dma_0
        raise RuntimeError(f"Could not resolve DMA for partition '{partition_name}'")

    def chain(self, partition_names):
        if not partition_names:
            raise ValueError("chain() requires at least one partition name")

        for name in partition_names:
            if name not in self._partitions:
                raise ValueError(
                    f"Unknown partition '{name}'. "
                    f"Available: {list(self._partitions.keys())}"
                )

        if self._switch is None:
            if len(partition_names) != 1:
                raise RuntimeError(
                    "axis_switch not found in design. "
                    "Multiple-partition chain() requires axis_switch: true in the YAML config."
                )
            return self._resolve_dma(partition_names[0])

        indices = [self._partitions[name] for name in partition_names]
        mapping = {}
        mapping[2 * indices[0]] = 2 * indices[0] + 1
        for k in range(len(indices) - 1):
            mapping[2 * indices[k + 1]] = 2 * indices[k]
        mapping[2 * indices[0] + 1] = 2 * indices[-1]

        self._switch.route(mapping)
        return self._resolve_dma(partition_names[0])

    def default_routing(self):
        if self._switch is not None:
            self._switch.default()


__all__ = ["Overlay", "allocate"]
