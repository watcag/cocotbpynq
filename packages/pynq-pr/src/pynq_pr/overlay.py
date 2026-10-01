"""
Overlay
Board-side driver for pynq-pr designs.

Deploy this file to the PYNQ board alongside bitstreams.  Import and use
instead of ``pynq.Overlay`` to get decoupling, ICAP, and axis_switch
routing handled automatically.

Example
-------
>>> from overlay import Overlay
>>> ol = Overlay("tutorial_z1.bit")
>>> ol.add.download("add_c_5.bit")
>>> ol.add.download("add_c_5.bin", icap=True)
>>> ol.pr_download("add", "add_c_5.bit")
>>> dma = ol.chain(["add", "sub"])
"""

import os

from pynq import DefaultHierarchy, DefaultIP, Overlay as _PynqOverlay, PL
from pynq.lib import AxiGPIO


# DefaultIP: AXI4-Stream Switch (PG085)
class AxisSwitch:
    """Runtime routing for AXI4-Stream Switch.

    Instantiated manually from ip_dict to avoid conflicts with PYNQ's
    built-in StreamSwitch driver which shares the same bindto string.
    """

    _CTRL_REG = 0x00
    _MI_MUX_BASE = 0x40
    _COMMIT = 0x2
    _DISABLE = 0x80000000

    def __init__(self, ip_info):
        from pynq import MMIO
        self._mmio = MMIO(ip_info["phys_addr"], ip_info["addr_range"])
        self.num_ports = int(ip_info["parameters"]["C_NUM_MI_SLOTS"])

    def write(self, offset, val):
        self._mmio.write(offset, val)

    def read(self, offset):
        return self._mmio.read(offset)

    def route(self, mapping):
        """Program the switch and commit.

        Parameters
        ----------
        mapping : dict
            {master_index: slave_index} for each active route.
            Unlisted masters are disabled.
        """
        for mi in range(self.num_ports):
            si = mapping.get(mi, self._DISABLE)
            self.write(self._MI_MUX_BASE + 4 * mi, si)
        self.write(self._CTRL_REG, self._COMMIT)

    def default(self):
        """Each RP independently wired to its own DMA."""
        mapping = {}
        for i in range(self.num_ports // 2):
            mapping[2 * i] = 2 * i + 1
            mapping[2 * i + 1] = 2 * i
        self.route(mapping)

    def disable(self):
        self.route({})


# DefaultHierarchy: per-RP hierarchy (contains dma + rp)
class PrPartition(DefaultHierarchy):
    """Driver for a single reconfigurable partition hierarchy."""

    @staticmethod
    def checkhierarchy(description):
        ips = description.get("ip", {})
        has_dma = any(
            d.get("type", "").startswith("xilinx.com:ip:axi_dma")
            for d in ips.values()
        )
        has_rp = "rp" in description.get("hierarchies", {})
        return has_dma and has_rp

    def download(self, partial_bit, method="pcap", icap=False):
        """Download a partial bitstream with automatic decoupling.

        Parameters
        ----------
        partial_bit : str
            Filename of the partial bitstream (.bit for pcap/fpga_manager,
            .bin for icap).
        method : str
            Reconfiguration method: "pcap", "fpga_manager", or "icap".
        icap : bool
            Legacy shorthand. If True, equivalent to method="icap".
        """
        if icap:
            method = "icap"
        ol = self._overlay
        if not isinstance(ol, Overlay):
            raise RuntimeError(
                "Partition not bound to a pynq-pr Overlay. "
                "Use overlay.Overlay instead of pynq.Overlay."
            )

        name = self.description["fullpath"]
        if name not in ol._partitions:
            raise RuntimeError(f"Partition '{name}' not registered.")

        bit_index = ol._partitions[name]
        mask = 1 << bit_index
        ol._decoupler.write(mask, mask)
        try:
            if method == "icap":
                ol._icap_download(self, partial_bit)
            elif method == "fpga_manager":
                ol._fpga_manager_download(partial_bit)
            else:
                self.rp.download(partial_bit)
        finally:
            ol._decoupler.write(0, mask)


# Overlay
class Overlay(_PynqOverlay):
    """Overlay subclass for pynq-pr designs.

    Wraps decoupling, axis_switch routing, and ICAP reconfiguration
    behind a simple API.
    """

    def __init__(self, bitfile_name, download=True, **kwargs):
        PL.reset()
        super().__init__(bitfile_name, download=download, **kwargs)

        self._decoupler = AxiGPIO(self.ip_dict["gpio_decouple"]).channel1
        self._partitions = {}
        self._icap_cache = {}
        self._fpga_mgr_cache = {}

        # Build a map from partition name to bit_index by parsing the HWH for
        # decouple_<name> xlslice DIN_FROM parameters — authoritative hardware mapping.
        import xml.etree.ElementTree as ET
        hwh_path = bitfile_name.replace(".bit", ".hwh")
        decouple_bits = {}
        for m in ET.parse(hwh_path).iter("MODULE"):
            if m.get("MODTYPE") == "xlslice":
                inst = m.get("INSTANCE", "")
                if inst.startswith("decouple_"):
                    din_from = next(
                        (p.get("VALUE") for p in m.iter("PARAMETER")
                         if p.get("NAME") == "DIN_FROM"), None
                    )
                    if din_from is not None:
                        decouple_bits[inst[len("decouple_"):]] = int(din_from)

        for name, desc in self.hierarchy_dict.items():
            driver = desc.get("driver")
            if driver is PrPartition or (
                isinstance(driver, type) and issubclass(driver, PrPartition)
            ):
                if name not in decouple_bits:
                    raise RuntimeError(
                        f"Could not find decouple xlslice for partition '{name}'."
                    )
                self._partitions[name] = decouple_bits[name]

        self._switch = None
        for ip_name, ip_desc in self.ip_dict.items():
            if ip_desc.get("type", "") == "xilinx.com:ip:axis_switch:1.1":
                self._switch = AxisSwitch(ip_desc)
                break

        if self._switch is not None:
            self._switch.default()

    def pr_download(self, partition_name, partial_bit, method="pcap", icap=False):
        """Download a partial bitstream by partition name.

        Parameters
        ----------
        partition_name : str
            Name of the partition hierarchy (e.g. "add", "sub").
        partial_bit : str
            Filename of the partial bitstream.
        method : str
            Reconfiguration method: "pcap", "fpga_manager", or "icap".
        icap : bool
            Legacy shorthand. If True, equivalent to method="icap".
        """
        if icap:
            method = "icap"
        if partition_name not in self._partitions:
            raise ValueError(
                f"Unknown partition '{partition_name}'. "
                f"Available: {list(self._partitions.keys())}"
            )
        getattr(self, partition_name).download(partial_bit, method=method)

    def chain(self, partition_names):
        """Route partitions in a pipeline and return (send_dma, recv_dma).

        Parameters
        ----------
        partition_names : list of str
            Ordered list of partition names from input to output.
            A single name routes that RP to its own DMA.
            Multiple names create a pipeline, e.g. ["add", "sub"]
            routes DMA -> add -> sub -> DMA.

        Returns
        -------
        dma : DMA
            DMA of the first partition. Use sendchannel to send and
            recvchannel to receive (last partition's output loops back here).
        """
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
            return getattr(self, partition_names[0]).dma

        indices = [self._partitions[n] for n in partition_names]
        mapping = {}

        # first partition: input from its own DMA
        mapping[2 * indices[0]] = 2 * indices[0] + 1

        # intermediate connections: output of [k] -> input of [k+1]
        for k in range(len(indices) - 1):
            mapping[2 * indices[k + 1]] = 2 * indices[k]

        # last partition: output back to first partition's DMA (S2MM)
        mapping[2 * indices[0] + 1] = 2 * indices[-1]

        self._switch.route(mapping)

        return getattr(self, partition_names[0]).dma

    def default_routing(self):
        """Restore default 1:1 RP-to-DMA routing."""
        if self._switch is not None:
            self._switch.default()

    def _fpga_manager_download(self, partial_bit):
        """Fast PCAP download via Linux fpga_manager sysfs interface.

        Preloads the .bit into a .bin via PYNQ's embedded_device helpers,
        then writes directly to the fpga_manager firmware path. The .bin
        conversion is cached for repeated downloads of the same file.
        """
        from pynq import Bitstream, Device
        from pynq.pl_server import embedded_device, xclbin_parser

        if partial_bit not in self._fpga_mgr_cache:
            bs = Bitstream(partial_bit, partial=True)
            parser = xclbin_parser.XclBin(
                xclbin_data=embedded_device.DEFAULT_XCLBIN
            )
            embedded_device._preload_binfile(bs, parser)
            self._fpga_mgr_cache[partial_bit] = bs

        bs = self._fpga_mgr_cache[partial_bit]
        dev = Device.active_device
        with open(dev.BS_FPGA_MAN_FLAGS, "w") as fd:
            fd.write("1")
        with open(dev.BS_FPGA_MAN, "w") as fd:
            fd.write(bs.binfile_name)

    def _pcap_to_icap(self):
        """Transfer configuration control from PCAP to ICAP (KV260 only)."""
        if os.path.exists("/sys/firmware/zynqmp/config_reg"):
            os.system("echo 0xFFCA3008 0x1 0x0 > /sys/firmware/zynqmp/config_reg")

    def _icap_download(self, partition, partial_bit):
        """ICAP download via versatile controller (axi3_ctrl)."""
        import numpy as np
        from pynq import allocate, MMIO

        self._pcap_to_icap()

        _PRG_BIT = 1 << 1
        _START_BIT = 1 << 0
        _READY_BIT = 1 << 2

        ctrl_key = None
        for k in self.ip_dict:
            if "axi3_ctrl" in k:
                ctrl_key = k
                break
        if ctrl_key is None:
            raise RuntimeError(
                "Versatile (ICAP) controller not found in design. "
                "Set reconfiguration_method: icap in the YAML config."
            )

        if not hasattr(self, "_icap_mmio"):
            info = self.ip_dict[ctrl_key]
            self._icap_mmio = MMIO(info["phys_addr"], info["addr_range"])

        if partial_bit not in self._icap_cache:
            with open(partial_bit, "rb") as f:
                bitstream = np.fromfile(f, dtype=np.uint32)
            padded = np.pad(bitstream, (250, 50), mode="constant")
            buf = allocate(shape=(len(padded),), dtype=np.uint32)
            buf[:] = padded
            size = len(padded)
            start_addr = buf.physical_address
            if size % 16 == 0:
                end_addr = start_addr + (32 * (size // 32 - 1) * 4)
                arlen = 15
            else:
                end_addr = start_addr + (32 * (size // 32) * 4)
                arlen = (size // 2) % 16 - 1
            self._icap_cache[partial_bit] = (start_addr, end_addr, arlen, buf)

        start_addr, end_addr, arlen, _ = self._icap_cache[partial_bit]

        ctrl = self._icap_mmio
        ctrl.write(0x04, start_addr)
        ctrl.write(0x08, end_addr)
        ctrl.write(0x00, (arlen << 2) | _PRG_BIT)
        ctrl.write(0x00, _START_BIT)
        ctrl.write(0x00, 0x00)
        while not (ctrl.read(0x00) & _READY_BIT):
            pass
