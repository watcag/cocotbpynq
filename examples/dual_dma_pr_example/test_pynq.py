"""
Dual-DMA, dual-RP PR example -- end-to-end cocotbpynq test.

Two independently-addressable reconfigurable partitions, each with its
own DMA channel and 3 RM variants:

    DMA0 (axi_dma_0) ↔ rp0:  add_one (x+1), double (x*2), negate (-x)
    DMA1 (axi_dma_1) ↔ rp1:  add_ten (x+10), triple (x*3), square (x*x)

The test exercises every RM variant on each partition independently,
verifying correct DMA streaming after each reconfiguration.
"""
import os
import numpy as np

COCOTB_IS_RUNNING = "COCOTB_SYS_ARGV" in os.environ

if not COCOTB_IS_RUNNING:
    from pynq import Overlay, allocate
else:
    import cocotbpynq
    from cocotbpynq import Overlay, allocate


def stream(dma, x, y):
    """Send x through a DMA channel, receive into y."""
    y[:] = 0
    dma.recvchannel.transfer(y)
    dma.sendchannel.transfer(x)
    dma.sendchannel.wait()
    dma.recvchannel.wait()


def check(tag, y, expected):
    """Assert and print result."""
    assert (y == expected).all(), \
        f"{tag}: expected {list(expected)}, got {list(y)}"
    print(f"[PASS] {tag}: {list(y)}")


def main(dut=None):
    overlay = Overlay('design.bit')

    dma0 = overlay.axi_dma_0
    dma1 = overlay.axi_dma_1

    x = allocate(shape=(6,), dtype=np.int32)
    y = allocate(shape=(6,), dtype=np.int32)
    x[:] = np.array([0, 1, 2, 3, 4, 5], dtype=np.int32)

    # ══════════════════════════════════════════════════════════════════════
    #  Partition 0 — all 3 RMs via DMA0
    # ══════════════════════════════════════════════════════════════════════

    # RP0 initial: add_one (x + 1)
    stream(dma0, x, y)
    check("rp0/add_one", y, x + 1)

    # RP0 → double (x * 2)
    print("Reconfiguring rp0 → double ...")
    overlay.pr_download('rp0', 'rp0_double')
    stream(dma0, x, y)
    check("rp0/double", y, x * 2)

    # RP0 → negate (-x)
    print("Reconfiguring rp0 → negate ...")
    overlay.pr_download('rp0', 'rp0_negate')
    stream(dma0, x, y)
    check("rp0/negate", y, -x)

    # ══════════════════════════════════════════════════════════════════════
    #  Partition 1 — all 3 RMs via DMA1
    # ══════════════════════════════════════════════════════════════════════

    # RP1 initial: add_ten (x + 10)
    stream(dma1, x, y)
    check("rp1/add_ten", y, x + 10)

    # RP1 → triple (x * 3)
    print("Reconfiguring rp1 → triple ...")
    overlay.pr_download('rp1', 'rp1_triple')
    stream(dma1, x, y)
    check("rp1/triple", y, x * 3)

    # RP1 → square (x * x)
    print("Reconfiguring rp1 → square ...")
    overlay.pr_download('rp1', 'rp1_square')
    stream(dma1, x, y)
    check("rp1/square", y, x * x)

    # ══════════════════════════════════════════════════════════════════════
    #  Cross-check: both partitions active with different RMs
    # ══════════════════════════════════════════════════════════════════════

    # RP0 is currently negate, RP1 is currently square
    # Reconfigure RP0 back to add_one, keep RP1 as square
    print("Reconfiguring rp0 → add_one (while rp1 stays square) ...")
    overlay.pr_download('rp0', 'rp0_add_one')

    y0 = allocate(shape=(6,), dtype=np.int32)
    y1 = allocate(shape=(6,), dtype=np.int32)

    stream(dma0, x, y0)
    check("cross/rp0=add_one", y0, x + 1)

    stream(dma1, x, y1)
    check("cross/rp1=square", y1, x * x)

    print(f"\n[PASS] All 8 tests passed — 6 RM variants across 2 partitions.")


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
