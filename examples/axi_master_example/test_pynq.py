"""
AXI master example -- a PL master reading and writing PS DDR (cocotbpynq.axi_mem).

The PYNQ code below runs UNCHANGED on:
  - A Zynq UltraScale+ PYNQ board with the memcpy_axi block design (python test_pynq.py)
  - Simulation (via run.py -> cocotb + Verilator), where the RTL's m_axi port reads and
    writes the allocated buffers through an HP-port model

memcpy_axi copies LEN bytes from SRC to DST with 16-beat bursts. The buffers are cacheable,
so the host must flush the source before the start and invalidate the destination after
DONE: the second and third tests leave one of them out and see the stale data the board
would show.
"""
import os

import numpy as np

COCOTB_IS_RUNNING = "COCOTB_SYS_ARGV" in os.environ

if not COCOTB_IS_RUNNING:
    from pynq import MMIO, Overlay, allocate
else:
    import cocotbpynq
    from cocotbpynq import MMIO, Overlay, allocate

IP_BASE, IP_RANGE = 0xA0000000, 0x10000
CTRL, STATUS, SRC, DST, LEN, IDMODE, BURSTS = 0x00, 0x04, 0x10, 0x18, 0x20, 0x24, 0x28
AFI_HP0, AFI_RDISSUE = 0xFD380000, 0x04
NBYTES = 4096


def copy(mmio, src, dst, idmode=0, flush=True, invalidate=True):
    if flush:
        src.flush()
    mmio.write(SRC, src.physical_address & 0xFFFFFFFF)
    mmio.write(SRC + 4, src.physical_address >> 32)
    mmio.write(DST, dst.physical_address & 0xFFFFFFFF)
    mmio.write(DST + 4, dst.physical_address >> 32)
    mmio.write(LEN, src.nbytes)
    mmio.write(IDMODE, idmode)
    mmio.write(CTRL, 1)
    polls = 0
    while not mmio.read(STATUS) & 2:
        polls += 1
        assert polls < 100000, "memcpy not done"
    st = mmio.read(STATUS)
    mmio.write(CTRL, 2)
    if invalidate:
        dst.invalidate()
    assert not st & 4, f"bad AXI response (STATUS {st:#x})"
    assert mmio.read(BURSTS) == src.nbytes // 128


def same(dst, src):
    bad = np.flatnonzero(dst != src)
    assert not bad.size, f"{bad.size} words differ, first at word {bad[0]}: {dst[bad[0]]:#x} != {src[bad[0]]:#x}"


def check_bus():
    """Simulation only: the master kept to the AXI rules and nothing is left in flight."""
    if COCOTB_IS_RUNNING:
        mem = cocotbpynq.axi_mem.memory
        assert not mem.errors, mem.errors[:4]
        assert mem.idle(), mem.outstanding()
        print("HP port:", mem.stats())


def setup():
    ol = Overlay("memcpy.bit")
    mmio = MMIO(IP_BASE, IP_RANGE)
    src = allocate(shape=(NBYTES // 4,), dtype=np.uint32, cacheable=True)
    dst = allocate(shape=(NBYTES // 4,), dtype=np.uint32, cacheable=True)
    src[:] = np.arange(src.size, dtype=np.uint32) * 2654435761 & 0xFFFFFFFF
    dst[:] = 0
    dst.flush()
    return ol, mmio, src, dst


def copy_flush_invalidate(dut=None):
    """flush, copy, invalidate: the destination holds the source; again with the read bursts on two IDs and the
    HP0 port limited to 2 outstanding reads through its AFI register (as on the board)."""
    ol, mmio, src, dst = setup()
    copy(mmio, src, dst)
    same(dst, src)
    dst[:] = 0
    dst.flush()
    MMIO(AFI_HP0, 0x20).write(AFI_RDISSUE, 1)       # 2 outstanding read commands on HP0
    copy(mmio, src, dst, idmode=1)
    same(dst, src)
    MMIO(AFI_HP0, 0x20).write(AFI_RDISSUE, 7)       # the reset value
    check_bus()
    print("[PASS] copy with flush / invalidate")


def missing_flush(dut=None):
    """No flush of the source: the engine reads DRAM, which still holds the zeros of the allocation."""
    ol, mmio, src, dst = setup()
    copy(mmio, src, dst, flush=False)
    assert not dst.any(), "the copy saw host writes that were never flushed"
    if COCOTB_IS_RUNNING:
        assert cocotbpynq.device_memory.stale_reads > NBYTES // 2   # the source bytes were read stale
    check_bus()
    print("[PASS] missing flush: stale source data copied")


def missing_invalidate(dut=None):
    """No invalidate of the destination: the host keeps seeing its own (cached) zeros."""
    ol, mmio, src, dst = setup()
    copy(mmio, src, dst, invalidate=False)
    assert not dst.any(), "the host saw device writes without an invalidate"
    dst.invalidate()
    same(dst, src)
    check_bus()
    print("[PASS] missing invalidate: stale destination until invalidate")


if __name__ == "__main__":
    copy_flush_invalidate()
    missing_flush()
    missing_invalidate()
elif COCOTB_IS_RUNNING:
    copy_flush_invalidate = cocotbpynq.synctest(copy_flush_invalidate)
    missing_flush = cocotbpynq.synctest(missing_flush)
    missing_invalidate = cocotbpynq.synctest(missing_invalidate)
