"""
HWH (Hardware HandOff) file generator for cocotbpynq integration.

Generates a synthetic Xilinx HWH XML file from a PRConfig's static_region
interface definitions, enabling cocotbpynq to discover AXI IP blocks and
drive them via MMIO / DMA without a real Vivado project.

Naming convention (must match the RTL):
  AXI-Lite interface named 'ctrl':
    ctrl_awaddr, ctrl_awvalid, ctrl_awready,
    ctrl_wdata, ctrl_wstrb, ctrl_wvalid, ctrl_wready,
    ctrl_bvalid, ctrl_bready, ctrl_bresp,
    ctrl_araddr, ctrl_arvalid, ctrl_arready,
    ctrl_rdata, ctrl_rvalid, ctrl_rready, ctrl_rresp

  AXI-Stream interface named 'x' (subordinate = DUT receives / send channel):
    x_tdata, x_tvalid, x_tready, x_tlast

  AXI-Stream interface named 'y' (manager = DUT sends / recv channel):
    y_tdata, y_tvalid, y_tready, y_tlast

The generated HWH has:
  - A 'pr_cocotb_top' MODULE (the DUT wrapper) with clock/reset PORTS
    and BUSINTERFACES for each interface
  - A stub 'processing_system7' MODULE whose MEMORYMAP/MEMRANGE entries
    point cocotbpynq's MMIO/DMA discovery at the correct addresses
  - One 'axi_dma' stub MODULE per paired send+recv AXI-Stream interface pair
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET
from xml.dom import minidom
import logging

logger = logging.getLogger(__name__)

# Logical → physical port name templates for each interface type
_AXIL_PORTMAPS = [
    ("AWADDR",  "{p}_awaddr"),
    ("AWVALID", "{p}_awvalid"),
    ("AWREADY", "{p}_awready"),
    ("WDATA",   "{p}_wdata"),
    ("WSTRB",   "{p}_wstrb"),
    ("WVALID",  "{p}_wvalid"),
    ("WREADY",  "{p}_wready"),
    ("BVALID",  "{p}_bvalid"),
    ("BREADY",  "{p}_bready"),
    ("BRESP",   "{p}_bresp"),
    ("ARADDR",  "{p}_araddr"),
    ("ARVALID", "{p}_arvalid"),
    ("ARREADY", "{p}_arready"),
    ("RDATA",   "{p}_rdata"),
    ("RVALID",  "{p}_rvalid"),
    ("RREADY",  "{p}_rready"),
    ("RRESP",   "{p}_rresp"),
]

_AXIS_PORTMAPS = [
    ("TDATA",  "{p}_tdata"),
    ("TVALID", "{p}_tvalid"),
    ("TREADY", "{p}_tready"),
    ("TLAST",  "{p}_tlast"),
]


class HwhGenerator:
    """
    Generates a cocotbpynq-compatible HWH XML file from PRConfig interface defs.

    Parameters
    ----------
    build_dir : str or Path
        Directory where the generated .hwh file will be written.
    """

    def __init__(self, build_dir: str):
        self.build_dir = Path(build_dir)

    def generate(
        self,
        design_name: str,
        interfaces: Dict[str, Dict[str, Any]],
        clock_name: str = "clk",
        reset_name: str = None,
        reset_active_low: bool = True,
        output_name: str = "design",
    ) -> Path:
        """
        Generate a HWH file.

        Parameters
        ----------
        design_name : str
            Name of the static region design (used as MODULE INSTANCE).
        interfaces : dict
            Interface definitions from static_region.interfaces in PRConfig.
            Each entry: {name: {type, direction, dw, aw, base_addr, addr_range, ...}}
        clock_name : str
            Clock port name on the DUT.
        reset_name : str
            Reset port name on the DUT.
        reset_active_low : bool
            True if reset is active-low (ACTIVE_LOW), False for ACTIVE_HIGH.
        output_name : str
            Base name for the output file (without extension).

        Returns
        -------
        Path
            Path to the generated .hwh file.
        """
        root = ET.Element("EDKSYSTEM", {
            "EDWVERSION": "1.2",
            "VIVADOVERSION": "2022.1",
        })

        ET.SubElement(root, "SYSTEMINFO", {
            "ARCH": "zynq",
            "BOARD": "www.digilentinc.com:pynq-z1:part0:1.0",
            "DEVICE": "7z020",
            "NAME": design_name,
            "PACKAGE": "clg400",
            "SPEEDGRADE": "-1",
        })

        modules_el = ET.SubElement(root, "MODULES")
        ps7_memranges: List[Dict] = []
        dma_modules: List[Dict] = []  # {instance, busname_send, busname_recv, base_addr, addr_range}

        # ── DUT module (pr_cocotb_top wrapping the static region) ──────────
        dut_el = ET.SubElement(modules_el, "MODULE", {
            "MODTYPE":      "pr_cocotb_top",
            "INSTANCE":     design_name,
            "FULLNAME":     f"/{design_name}",
            "IPTYPE":       "PERIPHERAL",
            "IS_ENABLE":    "1",
            "VLNV":         f"user.com:module_ref:{design_name}:1.0",
        })

        ports_el = ET.SubElement(dut_el, "PORTS")
        ET.SubElement(ports_el, "PORT", {
            "NAME":          clock_name,
            "DIR":           "I",
            "SIGIS":         "clk",
            "CLKFREQUENCY":  "100000000",
        })
        if reset_name:
            ET.SubElement(ports_el, "PORT", {
                "NAME":     reset_name,
                "DIR":      "I",
                "SIGIS":    "rst",
                "POLARITY": "ACTIVE_LOW" if reset_active_low else "ACTIVE_HIGH",
            })

        busifs_el = ET.SubElement(dut_el, "BUSINTERFACES")

        for iface_name, iface_def in (interfaces or {}).items():
            itype     = iface_def.get("type", "gpio")
            direction = iface_def.get("direction", "subordinate")
            prefix    = iface_def.get("port_prefix", iface_name)
            base_addr = iface_def.get("base_addr")
            addr_range = iface_def.get("addr_range", 0x10000)

            if itype == "axil":
                # AXI-Lite slave → cocotbpynq MMIO target
                is_slave = direction in ("subordinate", "input")
                busname  = f"ps7_0_{iface_name}"
                busif_el = ET.SubElement(busifs_el, "BUSINTERFACE", {
                    "NAME":      iface_name,
                    "BUSNAME":   busname,
                    "TYPE":      "SLAVE" if is_slave else "MASTER",
                    "VLNV":      "xilinx.com:interface:aximm:1.0",
                    "DATAWIDTH": str(iface_def.get("dw", 32)),
                })
                pm_el = ET.SubElement(busif_el, "PORTMAPS")
                for logical, phys_tmpl in _AXIL_PORTMAPS:
                    ET.SubElement(pm_el, "PORTMAP", {
                        "LOGICAL":  logical,
                        "PHYSICAL": phys_tmpl.format(p=prefix),
                    })

                if base_addr is not None:
                    high_addr = base_addr + addr_range  # exclusive end (matches cocotbpynq check)
                    ps7_memranges.append({
                        "INSTANCE":          design_name,
                        "BASEVALUE":         f"{base_addr:#010x}",
                        "HIGHVALUE":         f"{high_addr:#010x}",
                        "SLAVEBUSINTERFACE": iface_name,
                        "MASTERBUSINTERFACE": "M_AXI_GP0",
                        "MEMTYPE":           "REGISTER",
                    })

            elif itype == "axi":
                # Full AXI — treat like AXI-Lite for MMIO purposes
                is_slave = direction in ("subordinate", "input")
                busname  = f"ps7_0_{iface_name}"
                busif_el = ET.SubElement(busifs_el, "BUSINTERFACE", {
                    "NAME":      iface_name,
                    "BUSNAME":   busname,
                    "TYPE":      "SLAVE" if is_slave else "MASTER",
                    "VLNV":      "xilinx.com:interface:aximm:1.0",
                    "DATAWIDTH": str(iface_def.get("dw", 32)),
                })
                pm_el = ET.SubElement(busif_el, "PORTMAPS")
                for logical, phys_tmpl in _AXIL_PORTMAPS:
                    ET.SubElement(pm_el, "PORTMAP", {
                        "LOGICAL":  logical,
                        "PHYSICAL": phys_tmpl.format(p=prefix),
                    })
                if base_addr is not None:
                    high_addr = base_addr + addr_range  # exclusive end (matches cocotbpynq check)
                    ps7_memranges.append({
                        "INSTANCE":           design_name,
                        "BASEVALUE":          f"{base_addr:#010x}",
                        "HIGHVALUE":          f"{high_addr:#010x}",
                        "SLAVEBUSINTERFACE":  iface_name,
                        "MASTERBUSINTERFACE": "M_AXI_GP0",
                        "MEMTYPE":            "REGISTER",
                    })

            elif itype == "sb":
                # AXI-Stream — DMA channel
                # direction 'subordinate'/'input' = DUT receives (send channel)
                # direction 'manager'/'output'    = DUT sends   (recv  channel)
                is_target = direction in ("subordinate", "input")
                dma_inst = iface_def.get("dma_instance", "axi_dma_0")
                busname   = f"{dma_inst}_{iface_name}"

                busif_el = ET.SubElement(busifs_el, "BUSINTERFACE", {
                    "NAME":    iface_name,
                    "BUSNAME": busname,
                    "TYPE":    "TARGET"    if is_target else "INITIATOR",
                    "VLNV":    "xilinx.com:interface:axis:1.0",
                })
                pm_el = ET.SubElement(busif_el, "PORTMAPS")
                for logical, phys_tmpl in _AXIS_PORTMAPS:
                    ET.SubElement(pm_el, "PORTMAP", {
                        "LOGICAL":  logical,
                        "PHYSICAL": phys_tmpl.format(p=prefix),
                    })

                # Build a grouped DMA entry keyed by paired interface
                # (we look for a paired send+recv or just add individually)
                dma_base = iface_def.get("base_addr")
                dma_range = iface_def.get("addr_range", 0x10000)

                existing = next(
                    (d for d in dma_modules if d["instance"] == dma_inst), None
                )
                if existing is None:
                    dma_modules.append({
                        "instance":   dma_inst,
                        "base_addr":  dma_base,
                        "addr_range": dma_range,
                        "busifs":     [],
                    })
                    existing = dma_modules[-1]

                axi_type = "INITIATOR" if is_target else "TARGET"
                axis_name = "M_AXIS_MM2S" if is_target else "S_AXIS_S2MM"
                existing["busifs"].append({
                    "NAME":    axis_name,
                    "BUSNAME": busname,
                    "TYPE":    axi_type,
                    "VLNV":    "xilinx.com:interface:axis:1.0",
                })

        # ── axi_dma stub modules ────────────────────────────────────────────
        for dma in dma_modules:
            inst = dma["instance"]
            dma_el = ET.SubElement(modules_el, "MODULE", {
                "MODTYPE":   "axi_dma",
                "INSTANCE":  inst,
                "FULLNAME":  f"/{inst}",
                "IPTYPE":    "PERIPHERAL",
                "IS_ENABLE": "1",
                "VLNV":      "xilinx.com:ip:axi_dma:7.1",
            })
            dbif_el = ET.SubElement(dma_el, "BUSINTERFACES")
            for bif in dma["busifs"]:
                ET.SubElement(dbif_el, "BUSINTERFACE", {
                    "NAME":    bif["NAME"],
                    "BUSNAME": bif["BUSNAME"],
                    "TYPE":    bif["TYPE"],
                    "VLNV":    bif["VLNV"],
                })

            # AXI-Lite control port (S_AXI_LITE) so MMIO can address DMA regs
            if dma.get("base_addr") is not None:
                s_axil_busname = f"ps7_0_{inst}_lite"
                ET.SubElement(dbif_el, "BUSINTERFACE", {
                    "NAME":    "S_AXI_LITE",
                    "BUSNAME": s_axil_busname,
                    "TYPE":    "SLAVE",
                    "VLNV":    "xilinx.com:interface:aximm:1.0",
                })
                high = dma["base_addr"] + dma["addr_range"] - 1
                ps7_memranges.append({
                    "INSTANCE":           inst,
                    "BASEVALUE":          f"{dma['base_addr']:#010x}",
                    "HIGHVALUE":          f"{high:#010x}",
                    "SLAVEBUSINTERFACE":  "S_AXI_LITE",
                    "MASTERBUSINTERFACE": "M_AXI_GP0",
                    "MEMTYPE":            "REGISTER",
                })

        # ── processing_system7 stub ─────────────────────────────────────────
        ps7_el = ET.SubElement(modules_el, "MODULE", {
            "MODTYPE":   "processing_system7",
            "INSTANCE":  "processing_system7_0",
            "FULLNAME":  "/processing_system7_0",
            "IPTYPE":    "PERIPHERAL",
            "IS_ENABLE": "1",
            "IS_PL":     "FALSE",
            "VLNV":      "xilinx.com:ip:processing_system7:5.5",
        })
        if ps7_memranges:
            mmap_el = ET.SubElement(ps7_el, "MEMORYMAP")
            for mr in ps7_memranges:
                ET.SubElement(mmap_el, "MEMRANGE", {
                    "INSTANCE":           mr["INSTANCE"],
                    "BASEVALUE":          mr["BASEVALUE"],
                    "HIGHVALUE":          mr["HIGHVALUE"],
                    "SLAVEBUSINTERFACE":  mr["SLAVEBUSINTERFACE"],
                    "MASTERBUSINTERFACE": mr["MASTERBUSINTERFACE"],
                    "MEMTYPE":            mr.get("MEMTYPE", "REGISTER"),
                    "BASENAME":           "C_BASEADDR",
                    "HIGHNAME":           "C_HIGHADDR",
                    "IS_DATA":            "TRUE",
                    "IS_INSTRUCTION":     "FALSE",
                })

        # ── Serialise ───────────────────────────────────────────────────────
        self.build_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.build_dir / f"{output_name}.hwh"

        rough = ET.tostring(root, encoding="unicode")
        reparsed = minidom.parseString(rough)
        pretty = reparsed.toprettyxml(indent="  ", encoding="UTF-8")
        # minidom adds an extra XML declaration; write as bytes then decode
        out_path.write_bytes(pretty)

        logger.info(f"Generated HWH: {out_path}")
        return out_path
