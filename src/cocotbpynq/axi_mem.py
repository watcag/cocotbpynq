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

"""PS DDR as a PL AXI4 master sees it: the slave side of the Zynq HP / HPC / ACP ports.

Every buffer from ``allocate`` is part of one device memory at its physical address.
A PL master (an RTL ``m_axi`` port) reads and writes the buffers' *device view*,
``buf._dram``, which is what DRAM holds.  The host works on the *CPU view*, the array
itself.  For a cacheable buffer, the two views are separate arrays:

* the device sees a host write only after ``flush()`` / ``sync_to_device()``;
* the host sees a device write only after ``invalidate()`` / ``sync_from_device()``.

So a missing flush or invalidate gives the same stale data in simulation as on the
board.  A non-cacheable buffer is one array (writes are visible at once), unless
``set_cache_model("strict")`` (or ``COCOTBPYNQ_CACHE=strict``) makes every buffer
behave as cacheable, so a driver that relies on non-cacheable memory without its
flush / invalidate calls is caught too.  ``DeviceMemory.stale_reads`` counts device
reads of bytes whose CPU view differs (a host write not yet flushed).

Each port is an ``AxiSlavePort`` with HP-port-like timing (``HpPortConfig``):

* outstanding limits per direction (the AFI FM's RDISSUE / WRISSUE: 8 after reset);
* read latency (address to first beat) plus a random extra per burst, write
  response latency plus a random extra;
* back-pressure: the probability per cycle that ARREADY / AWREADY / WREADY is low;
* gaps between read beats (RVALID withheld with a probability per beat);
* write data accepted before its address (up to ``w_before_aw`` beats);
* reordering of read bursts and write responses across IDs (AXI keeps the order
  within one ID, so a master with a single ID sees none);
* stall injection: with ``stall_rate`` per cycle, the port freezes every channel for
  1 .. ``stall_len`` cycles (the DDR controller serving another port).

The ports of one clock share one coroutine: per cycle it drives the slave outputs
after the rising edge and samples the master in the ReadOnly phase, so a handshake
is what both sides see at the next edge.  Protocol errors of the master (a VALID
dropped before READY, a payload changed while waiting, WLAST on the wrong beat, a
burst over a 4 KB boundary, an address outside every buffer) are kept in
``AxiMemory.errors`` (and raise with ``strict=True``).

    mem = AxiMemory(dut.clk, dut.resetn)
    mem.add_port("m_axi", AxiBus.from_prefix(dut, "m_axi"), HpPortConfig(r_jitter=64))
    mem.start()
    ...
    mem.outstanding()      # {port: (reads, writes)} in flight now
"""

from __future__ import annotations

import dataclasses
import os
import random
import zlib
from dataclasses import dataclass, field

import numpy as np


# ------------------------------------------------------------------ device memory
class DeviceMemory:
    """The physical address space the PL masters see: the device views of the allocated buffers."""

    def __init__(self):
        self.regions = []                 # (start, end, uint8 device view, cpu view or None)
        self.stale_reads = 0              # device-read bytes whose CPU view differs (unflushed host writes)
        self.check_stale = True

    def add(self, phys: int, dram: np.ndarray, cpu: np.ndarray | None = None):
        d = np.asarray(dram).reshape(-1).view(np.uint8)
        c = None if cpu is None else np.asarray(cpu).reshape(-1).view(np.uint8)
        if c is not None and np.shares_memory(c, d):
            c = None
        self.regions.append((int(phys), int(phys) + d.size, d, c))
        self.regions.sort(key=lambda r: r[0])

    def remove(self, phys: int):
        self.regions = [r for r in self.regions if r[0] != int(phys)]

    def clear(self):
        self.regions = []
        self.stale_reads = 0

    def find(self, addr: int, n: int):
        """(device view, cpu view or None, offset) of the region holding [addr, addr + n), or None."""
        for s, e, d, c in self.regions:
            if s <= addr and addr + n <= e:
                return d, c, addr - s
        return None

    def read(self, addr: int, n: int) -> bytes | None:
        r = self.find(addr, n)
        if r is None:
            return None
        d, c, o = r
        if c is not None and self.check_stale:
            self.stale_reads += int(np.count_nonzero(d[o:o + n] != c[o:o + n]))
        return d[o:o + n].tobytes()

    def write(self, addr: int, data: bytes, strobe: int | None = None) -> bool:
        n = len(data)
        r = self.find(addr, n)
        if r is None:
            return False
        d, _, o = r
        if strobe is None or strobe == (1 << n) - 1:
            d[o:o + n] = np.frombuffer(data, dtype=np.uint8)
        else:
            for i in range(n):
                if (strobe >> i) & 1:
                    d[o + i] = data[i]
        return True


device_memory = DeviceMemory()


# ------------------------------------------------------------------ port timing
@dataclass
class HpPortConfig:
    """Timing of one slave port (cycles of the port's clock; probabilities per cycle or per beat)."""
    max_reads: int = 8               # read bursts in flight (AFI RDISSUE + 1; 8 after reset)
    max_writes: int = 8              # write bursts in flight, AW to B (AFI WRISSUE + 1)
    r_latency: int = 40              # AR handshake to the first R beat
    r_jitter: int = 0                # + uniform 0 .. r_jitter per burst
    b_latency: int = 20              # last W beat to B
    b_jitter: int = 0                # + uniform 0 .. b_jitter per burst
    arready_low: float = 0.0         # probability ARREADY is low in a cycle
    awready_low: float = 0.0
    wready_low: float = 0.0
    r_gap: float = 0.0               # probability RVALID is withheld before a beat
    w_before_aw: int = 0             # W beats accepted before their AW
    reorder: bool = False            # read bursts / B responses of different IDs out of order
    stall_rate: float = 0.0          # probability per cycle that a stall starts
    stall_len: int = 0               # a stall freezes all channels for 1 .. stall_len cycles
    seed: int | None = None          # None: from the port name and AxiMemory's seed

    @classmethod
    def parse(cls, text: str | None, base: "HpPortConfig | None" = None) -> "HpPortConfig":
        """'max_reads=4,r_jitter=200,reorder=1' over base (default the class defaults)."""
        cfg = dataclasses.replace(base) if base is not None else cls()
        if not text:
            return cfg
        types = {f.name: f.type for f in dataclasses.fields(cls)}
        for item in text.replace(";", ",").split(","):
            item = item.strip()
            if not item:
                continue
            k, _, v = item.partition("=")
            k = k.strip()
            if k not in types:
                raise ValueError(f"unknown HP port setting {k!r} (known: {', '.join(types)})")
            t = str(types[k])
            if "bool" in t:
                val = v.strip().lower() in ("1", "true", "yes", "on")
            elif "float" in t:
                val = float(v)
            elif k == "seed" and v.strip().lower() == "none":
                val = None
            else:
                val = int(v, 0)
            setattr(cfg, k, val)
        return cfg

    def describe(self) -> str:
        d = HpPortConfig()
        diff = [f"{f.name}={getattr(self, f.name)}" for f in dataclasses.fields(self)
                if getattr(self, f.name) != getattr(d, f.name)]
        return ",".join(diff) or "default"


# ------------------------------------------------------------------ bus adapter
_CHANNELS = {
    "AR": ("ARVALID", "ARREADY", "ARADDR", "ARLEN", "ARSIZE", "ARBURST", "ARID"),
    "R": ("RVALID", "RREADY", "RDATA", "RRESP", "RLAST", "RID"),
    "AW": ("AWVALID", "AWREADY", "AWADDR", "AWLEN", "AWSIZE", "AWBURST", "AWID"),
    "W": ("WVALID", "WREADY", "WDATA", "WSTRB", "WLAST"),
    "B": ("BVALID", "BREADY", "BRESP", "BID"),
}


class AxiBus:
    """The AXI4 signals of one master port, by logical name (ARVALID, RDATA, ...)."""

    def __init__(self, signals: dict, name: str = "axi"):
        self.name = name
        self.sig = {k.upper(): v for k, v in signals.items() if v is not None}
        self.has_read = all(k in self.sig for k in ("ARVALID", "ARREADY", "ARADDR", "RVALID", "RREADY", "RDATA"))
        self.has_write = all(k in self.sig for k in ("AWVALID", "AWREADY", "AWADDR", "WVALID", "WREADY", "WDATA",
                                                       "BVALID", "BREADY"))
        if not (self.has_read or self.has_write):
            raise ValueError(f"{name}: neither a read nor a write channel set ({sorted(self.sig)})")
        data = self.sig["RDATA"] if self.has_read else self.sig["WDATA"]
        self.data_bytes = len(data) // 8

    @classmethod
    def from_prefix(cls, dut, prefix: str) -> "AxiBus":
        """Signals named <prefix>_<lowercase logical name> (m_axi_arvalid, ...)."""
        sig = {}
        for names in _CHANNELS.values():
            for n in names:
                h = getattr(dut, f"{prefix}_{n.lower()}", None)
                if h is not None:
                    sig[n] = h
        return cls(sig, prefix)

    @classmethod
    def from_businterface(cls, cpbus) -> "AxiBus":
        """A cocotbpynq.dut.CocotbPynqBusInterface (its HWH PORTMAPS: attributes by logical name)."""
        sig = {n: getattr(cpbus, n) for names in _CHANNELS.values() for n in names if hasattr(cpbus, n)}
        return cls(sig, cpbus.portname)

    def get(self, name):
        return self.sig.get(name)


def _bit(h) -> bool:
    try:
        return bool(h.value)
    except ValueError:                   # X / Z
        return False


def _uint(h, default=0) -> int:
    try:
        return int(h.value.to_unsigned())
    except (ValueError, AttributeError):
        try:
            return int(h.value)
        except ValueError:
            return default


def _beat_addrs(addr: int, length: int, size: int, burst: int, nbytes: int):
    """Per beat (address, first byte lane, bytes) of an AXI burst (FIXED 0, INCR 1, WRAP 2)."""
    sz = 1 << size
    out = []
    aligned = addr & ~(sz - 1)
    if burst == 2:
        span = sz * length
        lo = addr & ~(span - 1)
    for i in range(length):
        if burst == 0:
            a = addr
        elif burst == 2:
            a = lo + ((addr - lo + i * sz) % span)
        else:
            a = addr if i == 0 else aligned + i * sz
        a0 = a if i == 0 or burst == 0 else a & ~(sz - 1)
        lane = a0 % nbytes
        n = sz - (a0 & (sz - 1)) if i == 0 else sz
        out.append((a0, lane, min(n, nbytes - lane)))
    return out


# ------------------------------------------------------------------ one port
class _Burst:
    __slots__ = ("id", "addr", "len", "size", "burst", "beat", "t", "beats", "resp", "awseen", "wdone")

    def __init__(self, id_, addr, length, size, burst, t, nbytes):
        self.id, self.addr, self.len, self.size, self.burst = id_, addr, length, size, burst
        self.beat, self.t = 0, t
        self.beats = _beat_addrs(addr, length, size, burst, nbytes)
        self.resp = 0
        self.awseen, self.wdone = True, False


class AxiSlavePort:
    """The slave side of one PL master port into the device memory (see the module docstring)."""

    def __init__(self, name: str, bus: AxiBus, cfg: HpPortConfig, memory: DeviceMemory, owner: "AxiMemory",
                 seed: int = 0):
        self.name, self.bus, self.cfg, self.mem, self.owner = name, bus, cfg, memory, owner
        self.nb = bus.data_bytes
        self.rng = random.Random(cfg.seed if cfg.seed is not None else zlib.crc32(f"{name}:{seed}".encode()))
        self.s = bus.sig
        self.reset_state()
        self.stats = dict(ar=0, r_beats=0, aw=0, w_beats=0, b=0, stall_cycles=0, max_reads=0, max_writes=0,
                          decerr=0)

    def reset_state(self):
        self.rq = []                      # accepted read bursts, in AR order
        self.rcur = None                  # the burst whose beat is presented (held until RREADY)
        self.r_show = False
        self.awq = []                     # accepted AWs whose B has not been handshaken (the outstanding writes)
        self.wpend = []                   # W beats accepted before their AW: (data, strb, last)
        self.bq = []                      # write responses ready from cycle t: [burst]
        self.bcur = None
        self.stall = 0
        self.drv = {}                     # last driven value per signal
        self.prev_ar = self.prev_aw = self.prev_w = None   # payload of a VALID waiting for READY
        self.rdy = dict(ar=False, aw=False, w=False)

    # -- outputs
    def _set(self, name, v):
        if self.drv.get(name) != v:
            self.s[name].value = v
            self.drv[name] = v

    def drive(self, cyc: int):
        cfg, rng = self.cfg, self.rng
        if self.stall == 0 and cfg.stall_rate and rng.random() < cfg.stall_rate:
            self.stall = rng.randint(1, max(1, cfg.stall_len))
        stalled = self.stall > 0
        if stalled:
            self.stall -= 1
            self.stats["stall_cycles"] += 1
        b = self.bus
        if b.has_read:
            ar = (not stalled and len(self.rq) < cfg.max_reads
                  and not (cfg.arready_low and rng.random() < cfg.arready_low))
            self.rdy["ar"] = ar
            self._set("ARREADY", int(ar))
            if not self.r_show:           # choose the next beat to present (a shown beat is held until RREADY)
                self.rcur = None
                if not stalled and not (cfg.r_gap and rng.random() < cfg.r_gap):
                    self.rcur = self._next_read(cyc)
                if self.rcur is not None:
                    bu = self.rcur
                    a, lane, n = bu.beats[bu.beat]
                    data = self.mem.read(a, n)
                    if data is None:
                        bu.resp = 3
                        data = bytes(n)
                    word = int.from_bytes(data, "little") << (8 * lane)
                    self.s["RDATA"].value = word
                    if "RLAST" in self.s:
                        self._set("RLAST", int(bu.beat == bu.len - 1))
                    if "RID" in self.s:
                        self._set("RID", bu.id)
                    if "RRESP" in self.s:
                        self._set("RRESP", bu.resp)
                    self.r_show = True
            self._set("RVALID", int(self.r_show))
        if b.has_write:
            aw = not stalled and len(self.awq) < cfg.max_writes and not (cfg.awready_low and rng.random() < cfg.awready_low)
            self.rdy["aw"] = aw
            self._set("AWREADY", int(aw))
            has_slot = any(not x.wdone for x in self.awq) or len(self.wpend) < cfg.w_before_aw
            w = not stalled and has_slot and not (cfg.wready_low and rng.random() < cfg.wready_low)
            self.rdy["w"] = w
            self._set("WREADY", int(w))
            if self.bcur is None and not stalled:
                self.bcur = self._next_b(cyc)
                if self.bcur is not None:
                    if "BID" in self.s:
                        self._set("BID", self.bcur.id)
                    if "BRESP" in self.s:
                        self._set("BRESP", self.bcur.resp)
            self._set("BVALID", int(self.bcur is not None))

    def _next_read(self, cyc):
        ready = [x for x in self.rq if x.t <= cyc]
        if not ready:
            return None
        if not self.cfg.reorder:
            return self.rq[0] if self.rq[0].t <= cyc else None
        # AXI: in order within an ID; a burst already started is finished first (no interleaving)
        for x in ready:
            if x.beat:
                return x
        heads, seen = [], set()
        for x in self.rq:
            if x.id not in seen:
                seen.add(x.id)
                if x.t <= cyc:
                    heads.append(x)
        return self.rng.choice(heads) if heads else None

    def _next_b(self, cyc):
        ready = [x for x in self.bq if x.t <= cyc]
        if not ready:
            return None
        if not self.cfg.reorder:
            return self.bq[0] if self.bq[0].t <= cyc else None
        heads, seen = [], set()
        for x in self.bq:
            if x.id not in seen:
                seen.add(x.id)
                if x.t <= cyc:
                    heads.append(x)
        return self.rng.choice(heads) if heads else None

    # -- sampling (ReadOnly phase: the handshakes of the coming edge)
    def sample(self, cyc: int):
        s, cfg = self.s, self.cfg
        if self.bus.has_read:
            if self.r_show and _bit(s["RREADY"]):
                bu = self.rcur
                bu.beat += 1
                self.stats["r_beats"] += 1
                self.r_show = False
                if bu.beat == bu.len:
                    self.rq.remove(bu)
            if _bit(s["ARVALID"]):
                pay = (_uint(s["ARADDR"]), _uint(s["ARLEN"]) if "ARLEN" in s else 0,
                       _uint(s["ARSIZE"]) if "ARSIZE" in s else (self.nb.bit_length() - 1),
                       _uint(s["ARBURST"], 1) if "ARBURST" in s else 1, _uint(s["ARID"]) if "ARID" in s else 0)
                if self.prev_ar is not None and self.prev_ar != pay:
                    self.owner.error(cyc, self.name, f"AR payload changed while waiting for ARREADY: {self.prev_ar} -> {pay}")
                if self.rdy["ar"]:
                    addr, ln, sz, bt, id_ = pay
                    self._check_burst(cyc, "AR", addr, ln + 1, sz, bt)
                    t = cyc + 1 + cfg.r_latency + (self.rng.randint(0, cfg.r_jitter) if cfg.r_jitter else 0)
                    if not cfg.reorder:       # one queue: data in AR order
                        t = max(t, self.rq[-1].t if self.rq else 0)
                    self.rq.append(_Burst(id_, addr, ln + 1, sz, bt, t, self.nb))
                    self.stats["ar"] += 1
                    self.stats["max_reads"] = max(self.stats["max_reads"], len(self.rq))
                    self.prev_ar = None
                else:
                    self.prev_ar = pay
            elif self.prev_ar is not None:
                self.owner.error(cyc, self.name, "ARVALID dropped before ARREADY")
                self.prev_ar = None
        if self.bus.has_write:
            if self.bcur is not None and _bit(s["BREADY"]):
                self.bq.remove(self.bcur)
                self.awq.remove(self.bcur)
                self.bcur = None
                self.stats["b"] += 1
            aw_hs = False
            if _bit(s["AWVALID"]):
                pay = (_uint(s["AWADDR"]), _uint(s["AWLEN"]) if "AWLEN" in s else 0,
                       _uint(s["AWSIZE"]) if "AWSIZE" in s else (self.nb.bit_length() - 1),
                       _uint(s["AWBURST"], 1) if "AWBURST" in s else 1, _uint(s["AWID"]) if "AWID" in s else 0)
                if self.prev_aw is not None and self.prev_aw != pay:
                    self.owner.error(cyc, self.name, f"AW payload changed while waiting for AWREADY: {self.prev_aw} -> {pay}")
                if self.rdy["aw"]:
                    aw_hs = pay
                    self.prev_aw = None
                else:
                    self.prev_aw = pay
            elif self.prev_aw is not None:
                self.owner.error(cyc, self.name, "AWVALID dropped before AWREADY")
                self.prev_aw = None
            if _bit(s["WVALID"]):
                data = _uint(s["WDATA"])
                strb = _uint(s["WSTRB"], (1 << self.nb) - 1) if "WSTRB" in s else (1 << self.nb) - 1
                last = _bit(s["WLAST"]) if "WLAST" in s else True
                pay = (data, strb, last)
                if self.prev_w is not None and self.prev_w != pay:
                    self.owner.error(cyc, self.name, "W payload changed while waiting for WREADY")
                if self.rdy["w"]:
                    self.prev_w = None
                    self.stats["w_beats"] += 1
                    tgt = next((x for x in self.awq if not x.wdone), None)
                    if tgt is None:
                        self.wpend.append(pay)
                    else:
                        self._wbeat(cyc, tgt, *pay)
                else:
                    self.prev_w = pay
            elif self.prev_w is not None:
                self.owner.error(cyc, self.name, "WVALID dropped before WREADY")
                self.prev_w = None
            if aw_hs:
                addr, ln, sz, bt, id_ = aw_hs
                self._check_burst(cyc, "AW", addr, ln + 1, sz, bt)
                bu = _Burst(id_, addr, ln + 1, sz, bt, 0, self.nb)
                self.awq.append(bu)
                self.stats["aw"] += 1
                self.stats["max_writes"] = max(self.stats["max_writes"], len(self.awq))
                while self.wpend and not bu.wdone:
                    self._wbeat(cyc, bu, *self.wpend.pop(0))

    def _wbeat(self, cyc, bu, data, strb, last):
        a, lane, n = bu.beats[bu.beat]
        raw = data.to_bytes(self.nb, "little")[lane:lane + n]
        st = (strb >> lane) & ((1 << n) - 1)
        if st and not self.mem.write(a, raw, st):
            bu.resp = 3
        bu.beat += 1
        if last != (bu.beat == bu.len):
            self.owner.error(cyc, self.name, f"WLAST {'early' if last else 'missing'} on beat {bu.beat} of {bu.len} "
                                             f"(AW {bu.addr:#x})")
        if bu.beat == bu.len:
            bu.wdone = True
            bu.t = cyc + 1 + self.cfg.b_latency + (self.rng.randint(0, self.cfg.b_jitter) if self.cfg.b_jitter else 0)
            if not self.cfg.reorder:
                bu.t = max(bu.t, self.bq[-1].t if self.bq else 0)
            self.bq.append(bu)

    def _check_burst(self, cyc, ch, addr, length, size, burst):
        if (1 << size) > self.nb:
            self.owner.error(cyc, self.name, f"{ch} size {1 << size} bytes wider than the bus")
        if burst == 1 and (addr >> 12) != ((addr + (length << size) - 1) >> 12):
            self.owner.error(cyc, self.name, f"{ch} burst {addr:#x} + {length} x {1 << size} crosses a 4 KB boundary")
        if self.mem.find(addr & ~((1 << size) - 1), 1) is None or \
                self.mem.find(addr + (length << size) - (1 << size), 1) is None:
            self.stats["decerr"] += 1
            self.owner.error(cyc, self.name, f"{ch} {addr:#x} ({length} beats) outside every allocated buffer")

    def outstanding(self):
        return len(self.rq), len(self.awq)


# ------------------------------------------------------------------ all ports of one clock
class AxiMemory:
    """The slave ports of one clock domain into the device memory, run by one coroutine."""

    def __init__(self, clk, rst=None, rst_active_low: bool = True, memory: DeviceMemory | None = None,
                 seed: int | None = None, strict: bool = False):
        self.clk, self.rst, self.rst_active_low = clk, rst, rst_active_low
        self.memory = memory if memory is not None else device_memory
        self.seed = int(os.environ.get("COCOTBPYNQ_AXI_SEED", "0"), 0) if seed is None else seed
        self.strict = strict
        self.ports: dict[str, AxiSlavePort] = {}
        self.errors = []                 # (cycle, port, message)
        self.cycle = 0
        self._task = None

    def add_port(self, name: str, bus: AxiBus, cfg: HpPortConfig | None = None) -> AxiSlavePort:
        p = AxiSlavePort(name, bus, cfg or HpPortConfig(), self.memory, self, self.seed)
        self.ports[name] = p
        for k in ("ARREADY", "RVALID", "AWREADY", "WREADY", "BVALID"):
            if k in bus.sig:
                bus.sig[k].value = 0
                p.drv[k] = 0
        return p

    def error(self, cyc, port, msg):
        self.errors.append((cyc, port, msg))
        if self.strict:
            raise AssertionError(f"{port} at cycle {cyc}: {msg}")

    def start(self):
        import cocotb
        if self._task is None:
            self._task = cocotb.start_soon(self._run())
        return self

    def _in_reset(self):
        if self.rst is None:
            return False
        try:
            v = bool(self.rst.value)
        except ValueError:
            return True
        return v != self.rst_active_low

    async def _run(self):
        from cocotb.triggers import ReadOnly, RisingEdge
        ports = list(self.ports.values())
        edge, ro = RisingEdge(self.clk), ReadOnly()
        while True:
            await edge
            if self._in_reset():
                for p in ports:
                    p.reset_state()
                    for k in ("ARREADY", "RVALID", "AWREADY", "WREADY", "BVALID"):
                        if k in p.s:
                            p._set(k, 0)
                self.cycle += 1
                continue
            cyc = self.cycle
            for p in ports:
                p.drive(cyc)
            await ro
            for p in ports:
                p.sample(cyc)
            self.cycle += 1

    def outstanding(self) -> dict:
        return {n: p.outstanding() for n, p in self.ports.items()}

    def idle(self) -> bool:
        return all(r == 0 and w == 0 and not p.wpend for n, p in self.ports.items() for r, w in [p.outstanding()])

    def stats(self) -> dict:
        return {n: dict(p.stats, config=p.cfg.describe()) for n, p in self.ports.items()}


# the AxiMemory the most recent Overlay attached to its DUT's master ports (None before one)
memory: AxiMemory | None = None
# HP port timing for the ports an Overlay attaches: the default, and per port (by DUT bus interface name or by
# the PS slave interface it connects to, e.g. "S_AXI_HP0_FPD"); COCOTBPYNQ_HP / COCOTBPYNQ_HP_<NAME> (the
# HpPortConfig.parse syntax) apply on top
default_config = HpPortConfig()
port_configs: dict[str, HpPortConfig] = {}


def config_for(name: str, ps_port: str | None = None) -> HpPortConfig:
    cfg = port_configs.get(name) or (port_configs.get(ps_port) if ps_port else None) or default_config
    cfg = HpPortConfig.parse(os.environ.get("COCOTBPYNQ_HP"), cfg)
    for key in (name, ps_port):
        if key:
            cfg = HpPortConfig.parse(os.environ.get(f"COCOTBPYNQ_HP_{key.upper()}"), cfg)
    return cfg
