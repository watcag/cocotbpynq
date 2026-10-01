"""Paper §5.1 running example: MatMul → GELU / Softmax pipeline.

Same test code runs on a PYNQ board and in cocotbpynq-pr simulation.
The only divergence is the import block, selected by COCOTB_IS_RUNNING.

Pipeline behaviour:
  rp0 = matmul(x) = x*3 + 5
  rp1 = gelu(x)   = (x >= 0) ? x*2 : 0
       | softmax(x) = (x*7) & 0xFF         (swapped via pr_download)

Tests (all exercised through ol.chain() — matches the paper listing):
  1. chain[rp0]          → y = matmul(x)
  2. chain[rp0, rp1]     → y = gelu(matmul(x))
  3. swap rp1 to softmax; chain[rp0, rp1] → y = softmax(matmul(x))
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
    dma.sendchannel.transfer(x)
    dma.recvchannel.transfer(y)
    dma.sendchannel.wait()
    dma.recvchannel.wait()


def main(dut=None):
    ol = Overlay("design.bit")

    x = allocate(shape=(6,), dtype=np.int32)
    y = allocate(shape=(6,), dtype=np.int32)
    x[:] = np.arange(1, 7, dtype=np.int32)     # [1..6]

    # Test 1: chain rp0 only → matmul(x) = x*3+5
    dma = ol.chain(["rp0"])
    stream(dma, x, y)
    expected = x * 3 + 5
    assert np.array_equal(y, expected), f"matmul: {list(y)} vs {list(expected)}"
    print(f"[PASS] matmul alone: {list(y)}")

    # Test 2: chain rp0 → rp1 with gelu
    dma = ol.chain(["rp0", "rp1"])
    stream(dma, x, y)
    expected = np.where(x * 3 + 5 >= 0, (x * 3 + 5) * 2, 0).astype(np.int32)
    assert np.array_equal(y, expected), f"matmul→gelu: {list(y)} vs {list(expected)}"
    print(f"[PASS] matmul→gelu: {list(y)}")

    # Test 3: swap rp1 to softmax, same chain
    ol.pr_download('rp1', 'softmax', icap=True)
    dma = ol.chain(["rp0", "rp1"])
    stream(dma, x, y)
    expected = ((x * 3 + 5) * 7) & 0xFF
    assert np.array_equal(y, expected), f"matmul→softmax: {list(y)} vs {list(expected)}"
    print(f"[PASS] matmul→softmax: {list(y)}")

    print("[PASS] All mm_pipeline tests passed.")


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
