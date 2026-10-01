"""
Multi-RP streaming PR example -- cocotbpynq DMA integration test.

Two-stage reconfigurable pipeline:
    DMA in (x) → stage1_rm → stage2_rm → DMA out (y)

Each stage is independently reconfigurable. The test reconfigures
each stage separately and verifies the composed pipeline output.

Test flow (x = [0, 1, 2, 3]):
  1. stage1=add_one, stage2=double  → y = (x+1)*2  = [2, 4, 6, 8]
  2. Reconfigure stage1 → double    → y = (x*2)*2  = [0, 4, 8, 12]
  3. Reconfigure stage2 → add_one   → y = (x*2)+1  = [1, 3, 5, 7]
  4. Reconfigure stage1 → add_one   → y = (x+1)+1  = [2, 3, 4, 5]
"""
import os
import numpy as np

COCOTB_IS_RUNNING = "COCOTB_SYS_ARGV" in os.environ

if not COCOTB_IS_RUNNING:
    from pynq import Overlay, allocate
else:
    import cocotbpynq
    from cocotbpynq import Overlay, allocate


def stream(overlay, x, y):
    """Send x through the pipeline, receive into y."""
    y[:] = 0
    overlay.axi_dma_0.recvchannel.transfer(y)
    overlay.axi_dma_0.sendchannel.transfer(x)
    overlay.axi_dma_0.sendchannel.wait()
    overlay.axi_dma_0.recvchannel.wait()


def main(dut=None):
    overlay = Overlay('design.bit')

    x = allocate(shape=(4,), dtype=np.int32)
    y = allocate(shape=(4,), dtype=np.int32)
    x[:] = np.arange(4, dtype=np.int32)

    # -- Test 1: stage1=add_one, stage2=double → y = (x+1)*2 ---------------
    stream(overlay, x, y)
    expected = (np.arange(4, dtype=np.int32) + 1) * 2
    assert (y == expected).all(), \
        f"Test 1: expected {list(expected)}, got {list(y)}"
    print(f"[PASS] (x+1)*2: x={list(x)} → y={list(y)}")

    # -- Reconfigure stage1 only: add_one → double --------------------------
    print("Reconfiguring rp_stage1: add_one → double ...")
    overlay.pr_download('rp_stage1', 's1_double')
    print("Reconfiguration complete.")

    # -- Test 2: stage1=double, stage2=double → y = (x*2)*2 = x*4 ----------
    stream(overlay, x, y)
    expected = np.arange(4, dtype=np.int32) * 4
    assert (y == expected).all(), \
        f"Test 2: expected {list(expected)}, got {list(y)}"
    print(f"[PASS] (x*2)*2: x={list(x)} → y={list(y)}")

    # -- Reconfigure stage2 only: double → add_one --------------------------
    print("Reconfiguring rp_stage2: double → add_one ...")
    overlay.pr_download('rp_stage2', 's2_add_one')
    print("Reconfiguration complete.")

    # -- Test 3: stage1=double, stage2=add_one → y = x*2+1 -----------------
    stream(overlay, x, y)
    expected = np.arange(4, dtype=np.int32) * 2 + 1
    assert (y == expected).all(), \
        f"Test 3: expected {list(expected)}, got {list(y)}"
    print(f"[PASS] x*2+1:   x={list(x)} → y={list(y)}")

    # -- Reconfigure stage1 back: double → add_one --------------------------
    print("Reconfiguring rp_stage1: double → add_one ...")
    overlay.pr_download('rp_stage1', 's1_add_one')
    print("Reconfiguration complete.")

    # -- Test 4: stage1=add_one, stage2=add_one → y = x+2 ------------------
    stream(overlay, x, y)
    expected = np.arange(4, dtype=np.int32) + 2
    assert (y == expected).all(), \
        f"Test 4: expected {list(expected)}, got {list(y)}"
    print(f"[PASS] x+1+1:   x={list(x)} → y={list(y)}")

    print("\n[PASS] All 4 tests passed.")


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
