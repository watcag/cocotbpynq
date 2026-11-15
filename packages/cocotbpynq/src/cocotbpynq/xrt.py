# cocotbpynq - a cocotb based emulation tool for PYNQ-targetting code
# Copyright (C) 2026 Nachiket Kapre
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

"""PYNQ on Alveo cards (XRT) in simulation.

A PYNQ host script for an Alveo card (``Overlay("design.xclbin")``, ``allocate(..., target=ol.HBM0)``,
``ol.<cu>.call(...)``, ``ol.<cu>.read/write``) runs unchanged against the RTL of the design's compute units:

* :func:`make_top` writes a Verilog top from the xclbin's metadata: every compute unit (CU), its AXI4-Stream
  connections (``--connectivity.sc``) wired up, and each CU's AXI-Lite control port and AXI4 master ports
  brought out as ``<cu>_<port>_<SIGNAL>``.
* :class:`Overlay` reads the same metadata in the test, drives each control port as an AXI-Lite master and
  serves each AXI4 master port from a memory model of the card's banks (HBM pseudo-channels, DDR, PLRAM).
* :func:`allocate` returns host buffers in a bank; ``sync_to_device``/``sync_from_device`` copy them to and from
  the memory model, as on the card.

Kernels start through their registers (args, then AP_START; ``wait`` polls AP_IDLE and writes AP_CONTINUE for
``ap_ctrl_chain``), the way PYNQ's register start path does.  Only the metadata of the xclbin is used, so an
xclbin built for any target (hw, hw_emu) works.
"""

import hashlib
import mmap
import re
import struct
from collections import deque

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.task import resume
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge
from xml.etree import ElementTree

from .simulator import synctest  # noqa: F401  (re-exported for host scripts)

_MEM_TYPES = ["DDR3", "DDR4", "DRAM", "STREAMING", "PREALLOCATED_GLOB", "ARE", "HBM", "BRAM", "URAM",
              "STREAMING_CONNECTION", "HOST", "PS_KERNEL"]
_CONTROL = {0: "ap_ctrl_hs", 1: "ap_ctrl_chain", 2: "ap_ctrl_none", 5: "fast_adapter"}


def read_xclbin(path):
    """The metadata of an xclbin: (uuid, kernels XML, memories, IP layout, connections)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:7] != b"xclbin2":
        raise ValueError(f"{path} is not an xclbin")
    header = 304  # magic, signature length, reserved, key block, unique id
    uuid = data[header + 112:header + 128].hex()
    nsec = struct.unpack_from("<I", data, header + 144)[0]
    sections = {}
    for i in range(nsec):
        kind, _, offset, size = struct.unpack_from("<I16s4xQQ", data, header + 152 + 40 * i)
        sections[kind] = data[offset:offset + size]
    xml = ElementTree.fromstring(sections[2].rstrip(b"\0"))  # EMBEDDED_METADATA
    mems = []
    topo = sections.get(6, b"\0" * 8)  # MEM_TOPOLOGY
    for i in range(struct.unpack_from("<i", topo)[0]):
        mtype, used, size_kb, base, tag = struct.unpack_from("<BB6xQQ16s", topo, 8 + 40 * i)
        mems.append({"idx": i, "tag": tag.split(b"\0")[0].decode(), "type": _MEM_TYPES[mtype], "used": used,
                     "size": size_kb * 1024, "base_address": base,
                     "streaming": _MEM_TYPES[mtype].startswith("STREAMING")})
    ips = []
    layout = sections.get(8, b"\0" * 8)  # IP_LAYOUT
    for i in range(struct.unpack_from("<i", layout)[0]):
        itype, props, base, name = struct.unpack_from("<IIQ64s", layout, 8 + 80 * i)
        ips.append({"type": itype, "control": _CONTROL.get((props >> 8) & 0xFF), "base": base,
                    "name": name.split(b"\0")[0].decode()})
    conn = sections.get(7, b"\0" * 4)  # CONNECTIVITY
    conns = [struct.unpack_from("<iii", conn, 4 + 12 * i) for i in range(struct.unpack_from("<i", conn)[0])]
    return uuid, xml, mems, ips, conns


def write_xclbin(path, xml, mems, connections):
    """Write a metadata-only xclbin (no bitstream), e.g. to simulate a design before it is linked.

    ``xml`` is the kernels description (EMBEDDED_METADATA, as v++ writes it: ``<kernel>`` elements with
    ``<port>``, ``<arg>`` and ``<instance><addrRemap base=...>``).  ``mems`` lists the memories as dicts with
    ``tag``, ``type`` (e.g. ``"HBM"``, ``"DDR4"``, ``"STREAMING_CONNECTION"``), ``base_address``, ``size`` (bytes)
    and ``used``.  ``connections`` lists ``(cu, arg name, memory tag)``: a pointer argument's bank, or for a
    stream connection the two ends of one ``STREAMING_CONNECTION`` memory.
    """
    root = ElementTree.fromstring(xml)
    ips, args = [], {}
    for kernel in root.iter("kernel"):
        control = {v: k for k, v in _CONTROL.items()}[kernel.get("hwControlProtocol", "ap_ctrl_hs")]
        for inst in kernel.iter("instance"):
            args[inst.get("name")] = (len(ips), {a.get("name"): int(a.get("id")) for a in kernel.iter("arg")})
            ips.append(struct.pack("<IIQ64s", 1, control << 8, int(inst.find("addrRemap").get("base"), 0),
                                   f"{kernel.get('name')}:{inst.get('name')}".encode()))
    tags = [m["tag"] for m in mems]
    sections = {
        2: xml.encode(),
        6: struct.pack("<i4x", len(mems)) + b"".join(
            struct.pack("<BB6xQQ16s", _MEM_TYPES.index(m["type"]), m.get("used", 1), m.get("size", 0) // 1024,
                        m.get("base_address", 0), m["tag"].encode()) for m in mems),
        8: struct.pack("<i4x", len(ips)) + b"".join(ips),
        7: struct.pack("<i", len(connections)) + b"".join(
            struct.pack("<iii", args[cu][1][arg], args[cu][0], tags.index(tag)) for cu, arg, tag in connections),
    }
    offset = 456 + 40 * len(sections)
    heads, body = b"", b""
    for kind, data in sections.items():
        heads += struct.pack("<I16s4xQQ", kind, b"", offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 8)
    length = offset + len(body)
    uuid = hashlib.md5(body).digest()
    header = struct.pack("<QQQHBBHH16s64s16s16sI4x", length, 0, 0, 0, 2, 1, 0, 0, b"", b"", uuid, b"",
                         len(sections))
    with open(path, "wb") as f:
        f.write(b"xclbin2\0" + struct.pack("<i", -1) + b"\xff" * 28 + b"\xff" * 256 + struct.pack("<Q", 0) +
                header + heads + body)
    return path


def describe(path):
    """PYNQ-style ``ip_dict`` and ``mem_dict`` of an xclbin.

    ``ip_dict[cu]`` has ``phys_addr``, ``hw_control_protocol``, ``cu_name`` (kernel:cu), ``registers``
    (CTRL and the scalar/pointer arguments by name, pointers with the ``memory`` tag they connect to),
    ``streams`` (stream arguments with ``direction`` and ``stream_id``) and ``ports`` (name, mode, width of the
    kernel's interfaces).
    """
    uuid, xml, mems, ips, conns = read_xclbin(path)
    ip_dict = {}
    for kernel in xml.iter("kernel"):
        protocol = kernel.get("hwControlProtocol", "ap_ctrl_hs")
        ports = {p.get("name"): {"mode": p.get("mode"), "width": int(p.get("dataWidth"))}
                 for p in kernel.iter("port")}
        registers = {}
        if protocol not in ("ap_ctrl_none", "user_managed"):
            registers["CTRL"] = {"address_offset": 0, "size": 32, "type": "unsigned int", "id": None}
        streams = {}
        for arg in kernel.iter("arg"):
            if int(arg.get("addressQualifier"), 0) == 4:
                mode = ports[arg.get("port")]["mode"]
                streams[arg.get("name")] = {"id": int(arg.get("id")), "port": arg.get("port"),
                                            "direction": "input" if mode == "read_only" else "output"}
            else:
                registers[arg.get("name")] = {"address_offset": int(arg.get("offset"), 0),
                                              "size": int(arg.get("size"), 0) * 8, "type": arg.get("type"),
                                              "id": int(arg.get("id")), "port": arg.get("port")}
        for inst in kernel.iter("instance"):
            remap = inst.find("addrRemap")
            name = inst.get("name")
            ip_dict[name] = {"phys_addr": int(remap.get("base"), 0), "addr_range": int(remap.get("range"), 0),
                             "type": kernel.get("vlnv"), "kernel": kernel.get("name"),
                             "hw_control_protocol": protocol, "fullpath": name, "xclbin_uuid": uuid,
                             "cu_name": kernel.get("name") + ":" + name, "ports": ports,
                             "registers": {k: dict(v) for k, v in registers.items()},
                             "streams": {k: dict(v) for k, v in streams.items()}}
    for argid, ipidx, memidx in conns:  # which bank or stream each argument connects to
        cu = ip_dict.get(ips[ipidx]["name"].partition(":")[2])
        if cu is None:
            continue
        for r in cu["registers"].values():
            if r["id"] == argid:
                r["memory"] = mems[memidx]["tag"]
        for s in cu["streams"].values():
            if s["id"] == argid:
                s["stream_id"] = mems[memidx]["tag"]
    return ip_dict, {m["tag"]: m for m in mems}


def _module_ports(sources, names):
    """{module: {port: (direction, width)}} for the named modules (pyslang)."""
    import pyslang

    comp = pyslang.ast.Compilation()
    for s in sources:
        comp.addSyntaxTree(pyslang.syntax.SyntaxTree.fromFile(str(s)))
    found = {}

    def visit(inst):
        if inst.name in names or inst.definition.name in names:
            found[inst.definition.name] = {
                p.name: ("input" if p.direction == pyslang.ast.ArgumentDirection.In else "output", p.type.bitWidth)
                for p in inst.body.portList}

    for inst in comp.getRoot().topInstances:
        visit(inst)
    missing = set(names) - set(found)
    if missing:
        raise ValueError(f"modules not found in the sources: {sorted(missing)}")
    return found


_AXIS = {"TDATA", "TVALID", "TREADY", "TLAST", "TKEEP", "TSTRB", "TUSER", "TID", "TDEST"}


def _signals(ports, prefix):  # module ports of one AXI4-Stream interface: {TDATA: port name, ...}
    pre = prefix.lower() + "_"
    return {p[len(pre):].upper(): p for p in ports
            if p.lower().startswith(pre) and p[len(pre):].upper() in _AXIS}


def make_top(xclbin, sources, out, top="xrt_top"):
    """Write a Verilog top for the compute units of ``xclbin`` (their modules are in ``sources``).

    Each CU is an instance of its kernel's module (same name as the kernel).  Stream arguments are wired per
    the xclbin's stream connections; ``ap_clk*`` and ``ap_rst_n*`` go to the top's ``ap_clk`` and ``ap_rst_n``;
    every other port of a CU (AXI-Lite control, AXI4 masters) becomes a top-level port ``<cu>_<port>``.
    Returns ``top``.
    """
    ip_dict, _ = describe(xclbin)
    modports = _module_ports(sources, {v["kernel"] for v in ip_dict.values()})
    decls, body, wires = ["input wire ap_clk", "input wire ap_rst_n"], [], {}
    for cu, d in ip_dict.items():
        for s in d["streams"].values():
            wires.setdefault(s["stream_id"], {})[s["direction"]] = (cu, s["port"])
    nets = {}  # (cu, module port) -> net
    for sid, ends in wires.items():
        if set(ends) != {"input", "output"}:
            raise ValueError(f"stream {sid} needs one producer and one consumer: {ends}")
        src = _signals(modports[ip_dict[ends["output"][0]]["kernel"]], ends["output"][1])
        dst = _signals(modports[ip_dict[ends["input"][0]]["kernel"]], ends["input"][1])
        for suf, p in dst.items():
            if suf in src:
                width = modports[ip_dict[ends["output"][0]]["kernel"]][src[suf]][1]
                body.append(f"  wire [{width - 1}:0] {sid}_{suf};")
                nets[(ends["output"][0], src[suf])] = f"{sid}_{suf}"
                nets[(ends["input"][0], p)] = f"{sid}_{suf}"
            elif modports[ip_dict[ends["input"][0]]["kernel"]][p][0] == "input":
                nets[(ends["input"][0], p)] = "'1"  # e.g. TKEEP the producer does not drive
    stream_ports = {(cu, p) for cu, d in ip_dict.items() for s in d["streams"].values()
                    for p in _signals(modports[d["kernel"]], s["port"]).values()}
    for cu, d in ip_dict.items():
        conns = []
        for p, (direction, width) in modports[d["kernel"]].items():
            if p.startswith("ap_clk"):
                net = "ap_clk"
            elif p.startswith("ap_rst_n"):
                net = "ap_rst_n"
            elif (cu, p) in nets:
                net = nets[(cu, p)]
            elif (cu, p) in stream_ports or p == "interrupt":
                net = ""
            else:
                net = f"{cu}_{p}"
                decls.append(f"{direction} wire [{width - 1}:0] {net}")
            conns.append(f"    .{p}({net})")
        body.append(f"  {d['kernel']} {cu} (\n" + ",\n".join(conns) + "\n  );")
    with open(out, "w") as f:
        f.write(f"// Generated by cocotbpynq.xrt.make_top from {xclbin}\n`timescale 1ns/1ps\n")
        f.write(f"module {top} (\n  " + ",\n  ".join(decls) + "\n);\n" + "\n".join(body) + "\nendmodule\n")
    return top


class _Banks:
    """The card's memory banks (sparse, zero-filled) and a bump allocator per bank."""

    def __init__(self, mem_dict):
        self.banks = sorted((m for m in mem_dict.values() if m["used"] and not m["streaming"]),
                            key=lambda m: m["base_address"])
        self.data = {}
        self.next = {}

    def find(self, address, n):
        for m in self.banks:
            if m["base_address"] <= address and address + n <= m["base_address"] + m["size"]:
                if m["idx"] not in self.data:
                    self.data[m["idx"]] = mmap.mmap(-1, m["size"])
                return self.data[m["idx"]], address - m["base_address"]
        raise MemoryError(f"no memory bank holds 0x{address:x}..0x{address + n:x}")

    def read(self, address, n):
        mem, off = self.find(address, n)
        return mem[off:off + n]

    def write(self, address, data):
        mem, off = self.find(address, len(data))
        mem[off:off + len(data)] = data

    def alloc(self, bank, n):
        off = self.next.get(bank["idx"], 0)
        if off + n > bank["size"]:
            raise MemoryError(f"{bank['tag']} is full")
        self.next[bank["idx"]] = off + (n + 4095) // 4096 * 4096
        return bank["base_address"] + off


class _AxiSlave:
    """Serves one AXI4 master port of a CU from the memory banks (INCR bursts, outstanding transactions)."""

    def __init__(self, dut, prefix, banks):
        self.sig = {s: getattr(dut, f"{prefix}_{s}") for s in
                    ("ARVALID", "ARREADY", "ARADDR", "ARLEN", "RVALID", "RREADY", "RDATA", "RLAST", "RRESP",
                     "AWVALID", "AWREADY", "AWADDR", "AWLEN", "WVALID", "WREADY", "WDATA", "WSTRB",
                     "BVALID", "BREADY", "BRESP")}
        for s in ("ARID", "RID", "AWID", "BID"):
            if hasattr(dut, f"{prefix}_{s}"):
                self.sig[s] = getattr(dut, f"{prefix}_{s}")
        self.banks = banks
        self.width = len(self.sig["RDATA"]) // 8
        self.clk = dut.ap_clk
        for s in ("ARREADY", "AWREADY", "WREADY"):
            self.sig[s].value = 1
        for s in ("RVALID", "BVALID", "RRESP", "BRESP"):
            self.sig[s].value = 0
        cocotb.start_soon(self._read())
        cocotb.start_soon(self._write())

    # Each cycle: after the edge, apply the transfers sampled before it, drive the outputs, then sample (ReadOnly)
    # which transfers the next edge completes.
    async def _read(self):
        s, bursts, beats, cur, ar, r = self.sig, deque(), deque(), None, None, False
        while True:
            await RisingEdge(self.clk)
            if r:
                cur = None
            if ar:
                bursts.append(ar)
            if cur is None and not beats and bursts:
                a, n, i = bursts.popleft()
                data = self.banks.read(a, n * self.width)
                beats.extend((int.from_bytes(data[k * self.width:(k + 1) * self.width], "little"), k == n - 1, i)
                             for k in range(n))
            if cur is None and beats:
                cur = beats.popleft()
                s["RDATA"].value, s["RLAST"].value = cur[0], int(cur[1])
                if "RID" in s:
                    s["RID"].value = cur[2]
            s["RVALID"].value = int(cur is not None)
            await ReadOnly()
            r = cur is not None and bool(s["RREADY"].value)
            ar = (int(s["ARADDR"].value), int(s["ARLEN"].value) + 1,
                  int(s["ARID"].value) if "ARID" in s else 0) if s["ARVALID"].value else None

    async def _write(self):
        s, bursts, data, resp, cur, aw, w, b = self.sig, deque(), deque(), deque(), None, None, None, False
        while True:
            await RisingEdge(self.clk)
            if b:
                cur = None
            if aw:
                bursts.append(aw)
            if w:
                data.append(w)
            while bursts and len(data) >= bursts[0][1]:
                a, n, i = bursts.popleft()
                for k in range(n):
                    word, strb = data.popleft()
                    v = word.to_bytes(self.width, "little")
                    if strb == (1 << self.width) - 1:
                        self.banks.write(a + k * self.width, v)
                    else:
                        for j in range(self.width):
                            if strb >> j & 1:
                                self.banks.write(a + k * self.width + j, v[j:j + 1])
                resp.append(i)
            if cur is None and resp:
                cur = resp.popleft()
                if "BID" in s:
                    s["BID"].value = cur
            s["BVALID"].value = int(cur is not None)
            await ReadOnly()
            b = cur is not None and bool(s["BREADY"].value)
            aw = (int(s["AWADDR"].value), int(s["AWLEN"].value) + 1,
                  int(s["AWID"].value) if "AWID" in s else 0) if s["AWVALID"].value else None
            w = (int(s["WDATA"].value), int(s["WSTRB"].value)) if s["WVALID"].value else None


class _AxiLite:
    """AXI-Lite master on one CU's control port (one access at a time)."""

    def __init__(self, dut, prefix):
        self.s = {n: getattr(dut, f"{prefix}_{n}") for n in
                  ("AWVALID", "AWREADY", "AWADDR", "WVALID", "WREADY", "WDATA", "WSTRB", "BVALID", "BREADY",
                   "ARVALID", "ARREADY", "ARADDR", "RVALID", "RREADY", "RDATA")}
        self.clk = dut.ap_clk
        for n in ("AWVALID", "WVALID", "BREADY", "ARVALID", "RREADY"):
            self.s[n].value = 0

    async def _until(self, name):  # wait for name high (sampled in ReadOnly); returns after the edge that takes it
        while True:
            await ReadOnly()
            if self.s[name].value:
                break
            await RisingEdge(self.clk)
        await RisingEdge(self.clk)

    async def write(self, offset, value):
        s = self.s
        s["AWADDR"].value, s["WDATA"].value, s["WSTRB"].value = offset, value & 0xFFFFFFFF, 0xF
        s["AWVALID"].value = s["WVALID"].value = 1
        aw = w = False
        while not (aw and w):
            await ReadOnly()
            ta, tw = not aw and bool(s["AWREADY"].value), not w and bool(s["WREADY"].value)
            await RisingEdge(self.clk)
            if ta:
                aw, s["AWVALID"].value = True, 0
            if tw:
                w, s["WVALID"].value = True, 0
        s["BREADY"].value = 1
        await self._until("BVALID")
        s["BREADY"].value = 0

    async def read(self, offset):
        s = self.s
        s["ARADDR"].value, s["ARVALID"].value = offset, 1
        await self._until("ARREADY")
        s["ARVALID"].value, s["RREADY"].value = 0, 1
        while True:
            await ReadOnly()
            if s["RVALID"].value:
                value = int(s["RDATA"].value)
                break
            await RisingEdge(self.clk)
        await RisingEdge(self.clk)
        s["RREADY"].value = 0
        return value


class WaitHandle:
    def __init__(self, ip):
        self.ip = ip

    def wait(self):
        while not self.ip.read(0) & 0x4:  # AP_IDLE
            pass
        if self.ip.hw_control_protocol == "ap_ctrl_chain":
            self.ip.write(0, 0x10)  # AP_CONTINUE releases ap_done for the next start


class ComputeUnit:
    """A compute unit: ``read``/``write`` of its registers, ``start``/``call`` with its arguments."""

    def __init__(self, dut, name, desc):
        self.name, self.description = name, desc
        self.hw_control_protocol = desc["hw_control_protocol"]
        self.registers = desc["registers"]
        self.args = [k for k, v in sorted(self.registers.items(), key=lambda kv: kv[1]["address_offset"])
                     if k != "CTRL"]
        ctrl = [p for p, v in desc["ports"].items() if v["mode"] == "slave"]
        self._bus = _AxiLite(dut, f"{name}_{ctrl[0].lower()}") if ctrl else None  # none: a stream-only kernel

    @resume
    async def read(self, offset=0):
        return await self._bus.read(offset)

    @resume
    async def write(self, offset, value):
        await self._bus.write(offset, value)

    def start(self, *args):
        if "CTRL" not in self.registers:
            raise RuntimeError(f"{self.name} ({self.hw_control_protocol}) cannot be started")
        for name, a in zip(self.args, args):
            r = self.registers[name]
            value = a.device_address if "*" in r["type"] else int(a)
            for k in range(0, r["size"], 32):
                self.write(r["address_offset"] + k // 8, (value >> k) & 0xFFFFFFFF)
        self.write(0, 1)  # AP_START
        return WaitHandle(self)

    def call(self, *args):
        self.start(*args).wait()


class Memory:
    """A memory bank of the card (``ol.HBM0``, ``ol.bank0``, ...): a target for :func:`allocate`."""

    def __init__(self, banks, desc):
        self.banks, self.desc = banks, desc
        self.idx, self.size, self.base_address = desc["idx"], desc["size"], desc["base_address"]

    def allocate(self, shape, dtype):
        buf = Buffer(shape, dtype)
        buf.banks, buf.memory = self.banks, self
        buf.device_address = self.banks.alloc(self.desc, buf.nbytes)
        return buf


class Buffer(np.ndarray):
    """Host buffer mirrored in a card memory bank (slices map to their part of it)."""

    def __array_finalize__(self, obj):
        if isinstance(obj, Buffer) and getattr(obj, "banks", None) is not None:
            self.banks, self.memory = obj.banks, obj.memory
            self.device_address = obj.device_address + (self.__array_interface__["data"][0] -
                                                        obj.__array_interface__["data"][0])

    def sync_to_device(self):
        self.banks.write(self.device_address, np.ascontiguousarray(self).tobytes())

    def sync_from_device(self):
        self[...] = np.frombuffer(self.banks.read(self.device_address, self.nbytes), self.dtype).reshape(self.shape)

    flush, invalidate = sync_to_device, sync_from_device

    @property
    def physical_address(self):
        return self.device_address

    def freebuffer(self):
        pass


_overlay = None


def allocate(shape, dtype="u4", target=None, **kwargs):
    """``pynq.allocate``: a buffer in ``target`` (a memory bank of the overlay; default: its only used bank)."""
    if target is None:
        banks = [m for m in _overlay.mem_dict.values() if m["used"] and not m["streaming"]]
        if len(banks) != 1:
            raise RuntimeError("several memories in the design: give the target")
        target = Memory(_overlay._banks, banks[0])
    return target.allocate(shape, dtype)


class Overlay:
    """``pynq.Overlay`` for an xclbin, on the top written by :func:`make_top` (``cocotb.top``).

    Starts the kernel clock (``period_ns``), holds ``ap_rst_n`` low for 16 cycles (as an xclbin load resets
    the kernels), and attaches a memory model to every AXI4 master port.  CUs and memory banks are attributes
    (``ol.vadd_1``, ``ol.HBM0``; bank names drop non-alphanumerics, as PYNQ does).
    """

    def __init__(self, bitfile_name, period_ns=4):
        global _overlay
        dut = cocotb.top
        self.bitfile_name = bitfile_name
        self.ip_dict, self.mem_dict = describe(bitfile_name)
        self._banks = _Banks(self.mem_dict)
        cocotb.start_soon(Clock(dut.ap_clk, period_ns, "ns").start())
        for cu, d in self.ip_dict.items():
            for p, v in d["ports"].items():
                if v["mode"] == "master":
                    _AxiSlave(dut, f"{cu}_{p.lower()}", self._banks)
        self._ips = {cu: ComputeUnit(dut, cu, d) for cu, d in self.ip_dict.items()}
        self._reset(dut)
        self._mems = {re.sub("[^A-Za-z0-9_]", "", k): Memory(self._banks, v) for k, v in self.mem_dict.items()
                      if v["used"] and not v["streaming"]}
        _overlay = self

    @resume
    async def _reset(self, dut):
        dut.ap_rst_n.value = 0
        await ClockCycles(dut.ap_clk, 16)
        dut.ap_rst_n.value = 1
        await ClockCycles(dut.ap_clk, 2)

    def __getattr__(self, key):
        if key in self.__dict__.get("_ips", {}):
            return self._ips[key]
        if key in self.__dict__.get("_mems", {}):
            return self._mems[key]
        raise AttributeError(f"Could not find IP or memory {key} in overlay")

    def free(self):
        pass
