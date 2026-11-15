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

"""The processing system around the DUT: Zynq-7000 (processing_system7) and Zynq UltraScale+
(zynq_ultra_ps_e, e.g. the KV260) block designs.

* ``ps_module`` / ``ip_dict``: the PS of an HWH and PYNQ's ``Overlay.ip_dict`` (every address
  range the PS master ports reach: phys_addr, addr_range, type, fullpath).
* ``ps_slave_port``: the PS slave interface (S_AXI_HP0_FPD, S_AXI_HPC0_FPD, S_AXI_HP0, ...) a
  DUT master bus interface connects to.
* ``AfiRegisters``: the AFI FM registers of the Zynq UltraScale+ HP / HPC ports (UG1087
  AFIFM): writing RDISSUE / WRISSUE (outstanding commands - 1) sets the outstanding limits
  of the matching cocotbpynq.axi_mem port, as the register does on the board.
* ``Clocks``: pynq.Clocks (the PL clock settings are recorded; the simulation clocks are
  those of the HWH).
* ``host``: the host timing model applied to every MMIO access (``HostModel``).
* ``simtime``: perf_counter / time / sleep in simulated seconds of the DUT clock, to use in
  place of the time module, so a host loop's timeouts and timings follow the simulation.
"""

from __future__ import annotations

import random
import time as _time

PS_MODTYPES = ("processing_system7", "zynq_ultra_ps_e")

# Zynq UltraScale+ AFI FM blocks (UG1087): PS slave interface -> register base
AFI_BASES = {"S_AXI_HPC0_FPD": 0xFD360000, "S_AXI_HPC1_FPD": 0xFD370000, "S_AXI_HP0_FPD": 0xFD380000,
             "S_AXI_HP1_FPD": 0xFD390000, "S_AXI_HP2_FPD": 0xFD3A0000, "S_AXI_HP3_FPD": 0xFD3B0000}
AFI_RDISSUE, AFI_WRISSUE = 0x04, 0x18


def ps_module(hwh_tree):
    for t in PS_MODTYPES:
        el = hwh_tree.find(f"./MODULES/MODULE[@MODTYPE='{t}']")
        if el is not None:
            return el
    raise RuntimeError("No processing system (processing_system7 or zynq_ultra_ps_e) in the HWH file")


def ip_dict(hwh_tree) -> dict:
    """PYNQ's Overlay.ip_dict: one entry per address range of the PS master ports."""
    ps = ps_module(hwh_tree)
    out = {}
    for mr in ps.findall("./MEMORYMAP/MEMRANGE"):
        inst = mr.get("INSTANCE")
        el = hwh_tree.find(f"./MODULES/MODULE[@INSTANCE='{inst}']")
        full = (el.get("FULLNAME") if el is not None else inst).lstrip("/")
        lo, hi = int(mr.get("BASEVALUE"), 16), int(mr.get("HIGHVALUE"), 16)
        out[full] = dict(phys_addr=lo, addr_range=hi - lo + 1, type=el.get("VLNV") if el is not None else "",
                         fullpath=full, mem_id=mr.get("SLAVEBUSINTERFACE"), state=None, interrupts={}, gpio={},
                         parameters={p.get("NAME"): p.get("VALUE")
                                     for p in (el.findall("./PARAMETERS/PARAMETER") if el is not None else [])})
    return out


def ps_slave_port(hwh_tree, busname: str) -> str | None:
    """The PS slave bus interface on the bus `busname` (a DUT master's BUSNAME), or None."""
    ps = ps_module(hwh_tree)
    for b in ps.findall("./BUSINTERFACES/BUSINTERFACE"):
        if b.get("TYPE") == "SLAVE" and b.get("BUSNAME") == busname:
            return b.get("NAME")
    return None


class AfiRegisters:
    """One AFI FM register block (UG1087) in front of an HP / HPC port: RDISSUE / WRISSUE set the outstanding
    limits of the axi_mem ports on that PS interface (reset value 7: 8 outstanding); other registers keep their
    written values."""

    def __init__(self, ps_port: str, ports):
        self.ps_port, self.ports = ps_port, list(ports)
        p0 = self.ports[0].cfg if self.ports else None
        self.regs = {AFI_RDISSUE: (p0.max_reads - 1) & 0xF if p0 else 7,
                     AFI_WRISSUE: (p0.max_writes - 1) & 0xF if p0 else 7}

    def read(self, offset):
        return self.regs.get(offset, 0)

    def write(self, offset, value):
        self.regs[offset] = int(value) & 0xFFFFFFFF
        for p in self.ports:
            if offset == AFI_RDISSUE:
                p.cfg.max_reads = (value & 0xF) + 1
            elif offset == AFI_WRISSUE:
                p.cfg.max_writes = (value & 0xF) + 1


afi_blocks: dict[int, AfiRegisters] = {}       # register base -> block (filled by Overlay)


class Clocks:
    """pynq.Clocks: PL clock settings are recorded only (the simulation runs the HWH clocks)."""
    fclk0_mhz = 100.0
    fclk1_mhz = 100.0
    fclk2_mhz = 100.0
    fclk3_mhz = 100.0
    cpu_mhz = 1200.0


class HostModel:
    """Host-side timing of the MMIO accesses (in cycles of the DUT clock), so a host loop can be run with the gaps
    a real CPU leaves between its register accesses:

      mmio_cycles  (lo, hi): idle cycles before every access (the PS-PL interconnect and the CPU), uniform
      write_delay  {offset: (lo, hi)} or {(offset, value): (lo, hi)}: extra idle cycles before a write to the
                   DUT's register at offset (with that value): e.g. the gap before a start bit
      compute      "none": host code between accesses takes no simulated time; "wall": the real time the host
                   code took since the previous access, x wall_scale, passes in simulation first

    Every inserted delay is appended to ``log`` as (cycle, offset, value or None, cycles)."""

    def __init__(self):
        self.mmio_cycles = (0, 0)
        self.write_delay = {}
        self.compute = "none"
        self.wall_scale = 1.0
        self.clock_hz = None              # for "wall": cycles per real second (default simtime.clock_hz)
        self.rng = random.Random(0)
        self.log = []
        self.keep_log = True
        self._t_last = None

    def seed(self, s):
        self.rng = random.Random(s)

    def delay(self, offset, value=None, write=False) -> int:
        n = 0
        lo, hi = self.mmio_cycles
        if hi:
            n += self.rng.randint(lo, hi)
        if write:
            r = self.write_delay.get((offset, value)) or self.write_delay.get(offset)
            if r:
                n += self.rng.randint(r[0], r[1])
        if self.compute == "wall" and self._t_last is not None:
            hz = self.clock_hz or simtime.clock_hz
            n += int((_time.perf_counter() - self._t_last) * self.wall_scale * hz)
        return n

    async def wait(self, cpdut, offset, value=None, write=False):
        """The delay before one access, in simulation (MMIO calls this first)."""
        n = self.delay(offset, value, write)
        if n:
            from cocotb.triggers import ClockCycles
            from cocotb.utils import get_sim_time
            if self.keep_log:
                self.log.append((int(get_sim_time("step")) // simtime.steps_per_cycle, offset,
                                 value if write else None, n))
            await ClockCycles(cpdut.clk, n)

    def done(self):
        self._t_last = _time.perf_counter()


host = HostModel()


class _SimTime:
    """time.perf_counter / time.time / time.sleep in simulated seconds: the DUT clock's cycles / clock_hz.
    clock_hz defaults to the HWH frequency of the DUT's first clock (set by Overlay)."""

    def __init__(self):
        self.clock_hz = 100e6
        self.steps_per_cycle = 1000

    def _seconds(self):
        from cocotb.utils import get_sim_time
        return get_sim_time("step") / self.steps_per_cycle / self.clock_hz

    def perf_counter(self):
        return _now()

    def time(self):
        return _now()

    def monotonic(self):
        return _now()

    def sleep(self, s):
        _sleep(s)

    def __getattr__(self, name):        # anything else (strftime, ...) from the real time module
        return getattr(_time, name)


def _resume(f):
    from cocotb.task import resume
    return resume(f)


@_resume
async def _now():
    return simtime._seconds()


@_resume
async def _sleep(s):
    from cocotb.triggers import Timer
    steps = int(s * simtime.clock_hz * simtime.steps_per_cycle)
    if steps > 0:
        await Timer(steps, "step")


simtime = _SimTime()


class Interrupt:
    """pynq.Interrupt for a level-high interrupt output of the DUT: "<instance>/<port>" (e.g. "engine/irq");
    wait() returns once the port is high."""

    def __init__(self, pinname):
        from .overlay import cptop
        self.pinname = pinname
        port = pinname.split("/")[-1]
        self.sig = getattr(cptop.dut, port)
        self.cpdut = cptop

    async def wait(self):
        _wait_high(self.sig, self.cpdut.clk)


@_resume
async def _wait_high(sig, clk):
    from cocotb.triggers import ReadOnly, RisingEdge
    while True:
        await ReadOnly()
        try:
            if bool(sig.value):
                break
        except ValueError:
            pass
        await RisingEdge(clk)
    await RisingEdge(clk)
