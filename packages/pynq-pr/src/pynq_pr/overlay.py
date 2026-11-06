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

On Versal (VD100) the static design boots with the board (BOOT.BIN), so the
overlay attaches to it, and the PLM loads partial PDIs from DDR on request
(see Plm):

>>> ol = Overlay("tutorial_vd100.pdi")
>>> ol.pr_download("add", "add_c_5.pdi")
"""

import glob
import os
import threading
import time
import warnings

import numpy as np
from pynq import DefaultHierarchy, DefaultIP, MMIO, Overlay as _PynqOverlay, PL, allocate
from pynq.lib import AxiGPIO

# Versal Gen 1 part prefixes (AI Core, AI Edge, Prime, Premium, HBM): the IPI address map Plm uses.
_VERSAL_GEN1 = ("xcvc", "xcve", "xcvm", "xcvp", "xcvh")


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


class NocRoute:
    """Runtime routing for the NoC interconnect (noc_interconnect: true).

    The rps_route GPIO holds one destination field per source, w bits each
    (w = bits for 2N endpoints; field s at bits [w*s, w*s+w)). Endpoint 2i is
    partition i and 2i+1 is DMA i, as on the AXI4-Stream switch. A source
    takes its destination at a packet's first beat, so a route written
    mid-packet applies from the next packet.
    """

    def __init__(self, ip_info, num_partitions):
        self._gpio = AxiGPIO(ip_info).channel1
        self._n_end = 2 * num_partitions
        self._w = max(1, (self._n_end - 1).bit_length())

    def route(self, mapping):
        """Program the routes.

        Parameters
        ----------
        mapping : dict
            {destination: source}, as for AxisSwitch.route. Unlisted
            sources keep their default route (partition i <-> DMA i), unlike
            on the switch, where they are disabled; an idle source sends
            nothing, so its route is harmless. The NoC connects every source
            to every destination except itself and DMA to DMA.
        """
        dest = {s: s ^ 1 for s in range(self._n_end)}
        for d, s in mapping.items():
            if d == s or (d % 2 and s % 2):
                raise ValueError(f"no NoC path from endpoint {s} to endpoint {d}")
            dest[s] = d
        value = sum(d << (self._w * s) for s, d in dest.items())
        self._gpio.write(value, (1 << (self._w * self._n_end)) - 1)

    def default(self):
        """Each RP independently wired to its own DMA."""
        self.route({})


class Plm:
    """Versal Gen 1 platform loader and manager (PLM), reached over IPI channel 3.

    A request goes into the channel's message buffer for the PMC; setting the
    PMC's trigger bit interrupts the PLM, which writes its response after the
    request and clears the bit (for a PDI load, once the load has finished).
    pynq-pr's Versal shells give channel 3 to the A72 cores; Linux reaches the
    PLM through TF-A on channel 0, so the two do not share a buffer. Requests are
    serialized within a process; one process at a time may own the channel, as
    one process owns the overlay. Requests carry no CRC (a PLM built with
    ENABLE_IPI_CRC rejects them). Addresses (Gen 1 only; Versal Net and Gen 2
    differ) and command formats: Versal TRM (AM011, IPI) and the PLM's
    xilplmi/xilloader sources.
    """

    _IPI3 = 0xFF360000              # channel 3 registers
    _MSG_RAM = 0xFF3F0000           # IPI message buffers
    # Buffer from channel 3 (buffer index 5) to the PMC (index 1): 32-byte request, then 32-byte response
    _SLOT = 5 * 0x200 + 1 * 0x40
    _TRIG, _OBS, _PMC_BIT = 0x00, 0x04, 1 << 1
    _MAX_ARGS = 6                   # 8-word request: header, arguments, CRC word

    _GENERIC, _EVENT_LOGGING = 1, 19
    _LOADER, _FEATURES, _LOAD_PDI, _PDI_SRC_DDR = 7, 0, 1, 0xF

    _lock = threading.Lock()

    def __init__(self, timeout=5.0):
        claimed = glob.glob("/sys/bus/platform/devices/ff360000.*")
        if claimed:
            raise RuntimeError(f"PLM: IPI channel 3 is claimed by the Linux device {claimed[0]}")
        self._regs = MMIO(self._IPI3, 0x8)
        self._msg = MMIO(self._MSG_RAM, 0x1000)
        self._timeout = timeout

    def call(self, module, command, *args):
        """Send one command and return the six response words after the status."""
        if len(args) > self._MAX_ARGS:
            raise ValueError(f"PLM: at most {self._MAX_ARGS} arguments per command")
        with self._lock:
            if self._regs.read(self._OBS) & self._PMC_BIT:
                raise RuntimeError("PLM: an earlier request on IPI channel 3 has not been answered "
                                   "(an interrupted load still running, or a PLM that does not serve the channel)")
            words = [(len(args) << 16) | (module << 8) | command, *args]
            for i in range(8):
                self._msg.write(self._SLOT + 4 * i, words[i] if i < len(words) else 0)
            # The trigger is written after the request, through device memory, as TF-A does.
            self._regs.write(self._TRIG, self._PMC_BIT)
            deadline = time.monotonic() + self._timeout
            while self._regs.read(self._OBS) & self._PMC_BIT:
                if time.monotonic() > deadline:
                    raise TimeoutError("PLM: no response on IPI channel 3")
            response = [self._msg.read(self._SLOT + 0x20 + 4 * i) for i in range(7)]
        if response[0]:
            detail = " ".join(f"{w:#x}" for w in response[1:3])
            raise RuntimeError(f"PLM: command {module}.{command} failed: status {response[0]:#x} ({detail})")
        return response[1:]

    def check_loader(self):
        """Raise unless the PLM's loader answers on this channel and serves PDI loads."""
        if self.call(self._LOADER, self._FEATURES, self._LOAD_PDI)[0] != 0:
            raise RuntimeError("PLM: the loader does not support loading PDIs")

    def disable_uart(self):
        """Stop the PLM's console output until reboot or enable_uart().

        The PLM waits for every line it prints at 115200 baud, which adds tens of
        milliseconds to each partial load. Its log buffer in memory keeps the messages.
        """
        self.call(self._GENERIC, self._EVENT_LOGGING, 8, 0, 1, 0)  # configure UART: current, disabled

    def enable_uart(self):
        """Restore the PLM's console output."""
        self.call(self._GENERIC, self._EVENT_LOGGING, 8, 0, 0, 0)  # configure UART: current, enabled

    def load_pdi(self, address):
        """Load the PDI at a physical DDR address; returns when it is loaded."""
        self.call(self._LOADER, self._LOAD_PDI, self._PDI_SRC_DDR, address >> 32, address & 0xFFFFFFFF)


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

        If the load fails or is interrupted, the partition stays decoupled: it
        may be partly configured, and is reconnected by the next successful load.
        """
        if icap:
            method = "icap"
        ol = self._overlay
        if not isinstance(ol, Overlay):
            raise RuntimeError(
                "Partition not bound to a pynq-pr Overlay. "
                "Use overlay.Overlay instead of pynq.Overlay."
            )
        if ol._versal and method == "icap":
            raise ValueError("Versal has no ICAP: partials are loaded by the PLM")

        name = self.description["fullpath"]
        if name not in ol._partitions:
            raise RuntimeError(f"Partition '{name}' not registered.")

        bit_index = ol._partitions[name]
        mask = 1 << bit_index
        ol._decoupler.write(mask, mask)
        if ol._versal:
            ol._pdi_download(partial_bit)
        elif method == "icap":
            ol._icap_download(self, partial_bit)
        elif method == "fpga_manager":
            ol._fpga_manager_download(partial_bit)
        else:
            self.rp.download(partial_bit)
        ol._decoupler.write(0, mask)


# Overlay
class Overlay(_PynqOverlay):
    """Overlay subclass for pynq-pr designs.

    Wraps decoupling, axis_switch routing, and ICAP reconfiguration
    behind a simple API.
    """

    def __init__(self, bitfile_name, download=True, **kwargs):
        # Versal: the static design booted with the board (BOOT.BIN) and cannot be
        # reloaded from Linux, so attach to it.
        bitfile_name = os.fspath(bitfile_name)
        self._versal = bitfile_name.endswith(".pdi")
        self.partial_ext = ".pdi" if self._versal else ".bit"
        if self._versal:
            download = False
            # An absolute path skips PYNQ's search of installed overlay packages, which the
            # Versal PYNQ bundle does not ship (pynq.overlays).
            bitfile_name = os.path.abspath(bitfile_name)
        else:
            PL.reset()
        super().__init__(bitfile_name, download=download, **kwargs)

        self._decoupler = AxiGPIO(self.ip_dict["gpio_decouple"]).channel1
        self._partitions = {}
        self._icap_cache = {}
        self._fpga_mgr_cache = {}
        self._pdi_buffers = {}

        # Build a map from partition name to bit_index by parsing the HWH for
        # decouple_<name> xlslice DIN_FROM parameters — authoritative hardware mapping.
        import xml.etree.ElementTree as ET
        hwh_path = os.path.splitext(bitfile_name)[0] + ".hwh"
        hwh = ET.parse(hwh_path)
        decouple_bits = {}
        for m in hwh.iter("MODULE"):
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
        if self._switch is None and "rps_route" in self.ip_dict:
            self._switch = NocRoute(self.ip_dict["rps_route"], len(self._partitions))

        if self._switch is not None:
            self._switch.default()

        if self._versal:
            device = hwh.find("SYSTEMINFO").get("DEVICE", "")
            if not device.startswith(_VERSAL_GEN1):
                raise NotImplementedError(f"pynq-pr loads partials on Versal Gen 1 devices only, not {device}")
            self._plm = Plm()
            self._plm.check_loader()  # fails here, not at the first load, if the PLM does not answer
            try:
                self._plm.disable_uart()
            except RuntimeError as e:  # e.g. no PLM console: loads are still correct
                warnings.warn(f"PLM console output left on, loads are slower: {e}")

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

    def _pdi_download(self, partial_pdi):
        """Versal: have the PLM load a partial PDI from DDR.

        The PDI is copied into a DMA buffer on its first load, and again only if the
        file changes, so later loads copy nothing; the buffers live as long as the
        overlay. The PLM checks that its parent ID is the running static design's
        and quiesces the partition's NoC endpoints while it loads it.
        """
        stat = os.stat(partial_pdi)
        if stat.st_size % 4:
            raise ValueError(f"{partial_pdi}: not a PDI (size is not a multiple of 4 bytes)")
        version = (stat.st_mtime_ns, stat.st_size)
        cached = self._pdi_buffers.get(partial_pdi)
        if cached is None or cached[0] != version:
            data = np.fromfile(partial_pdi, dtype=np.uint32)
            buf = allocate(shape=data.shape, dtype=np.uint32)
            buf[:] = data
            buf.flush()
            cached = self._pdi_buffers[partial_pdi] = (version, buf)
        self._plm.load_pdi(cached[1].physical_address)

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
