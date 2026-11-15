"""cocotbpynq.axi_mem: the HP-port model of PS DDR for PL AXI4 masters.

Host-only checks of the burst addressing, the settings parser and the cache model of the
buffers, then the axi_master example (memcpy_axi on Verilator) at the HP port's reset timing
and under random latency, back-pressure, beat gaps, stalls and reordering.

    pip install ".[test]" verilator && pytest tests/test_axi_mem.py
"""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from cocotbpynq import allocate, device_memory, set_cache_model
from cocotbpynq.axi_mem import HpPortConfig, _beat_addrs

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "axi_master_example"


def test_beat_addresses():
    # INCR, full width, aligned
    assert _beat_addrs(0x1000, 4, 4, 1, 16) == [(0x1000, 0, 16), (0x1010, 0, 16), (0x1020, 0, 16), (0x1030, 0, 16)]
    # INCR, narrow (4 bytes on a 16-byte bus), unaligned start: the first beat is the rest of its word
    assert _beat_addrs(0x1006, 3, 2, 1, 16) == [(0x1006, 6, 2), (0x1008, 8, 4), (0x100C, 12, 4)]
    # FIXED repeats the address, WRAP wraps at the burst span
    assert [a for a, _, _ in _beat_addrs(0x40, 3, 3, 0, 8)] == [0x40] * 3
    assert [a for a, _, _ in _beat_addrs(0x18, 4, 3, 2, 8)] == [0x18, 0x0, 0x8, 0x10]


def test_parse():
    c = HpPortConfig.parse("max_reads=4, r_jitter=0x10,reorder=1,arready_low=0.25")
    assert (c.max_reads, c.r_jitter, c.reorder, c.arready_low) == (4, 16, True, 0.25)
    assert HpPortConfig.parse("b_latency=3", c).max_reads == 4
    assert "max_reads=4" in c.describe()
    with pytest.raises(ValueError):
        HpPortConfig.parse("nonsense=1")


def test_cache_model():
    a = allocate(shape=(64,), dtype=np.uint8, cacheable=True)
    a[:] = 7
    assert device_memory.read(a.physical_address, 4) == bytes(4)        # not flushed: DRAM still zero
    assert a.unflushed_bytes() == 64
    a.flush()
    assert device_memory.read(a.physical_address, 4) == bytes([7] * 4)
    device_memory.write(a.physical_address, bytes([1, 2, 3, 4]))       # a PL master writes DRAM
    assert a[0] == 7                                                     # the host still sees its cache
    a.invalidate()
    assert list(a[:4]) == [1, 2, 3, 4]
    b = allocate(shape=(16,), dtype=np.uint8, cacheable=False)           # one array: no flush needed
    b[:] = 9
    assert device_memory.read(b.physical_address, 2) == bytes([9, 9])
    set_cache_model("strict")                                            # every buffer keeps a device view
    try:
        c = allocate(shape=(16,), dtype=np.uint8, cacheable=False)
        c[:] = 5
        assert device_memory.read(c.physical_address, 2) == bytes(2)
    finally:
        set_cache_model("pynq")
    a.freebuffer()
    assert device_memory.find(a.physical_address, 1) is None


def _example():
    spec = importlib.util.spec_from_file_location("axi_master_run", EXAMPLE / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("hp,seed", [("", 0), ("stress", 1), ("max_reads=1,max_writes=1,r_latency=0,b_latency=0", 0)])
def test_axi_master_example(hp, seed, tmp_path):
    assert _example().main(hp, seed, str(tmp_path / "sim_build")) == 0
