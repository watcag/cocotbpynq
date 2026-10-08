"""PYNQ host code for an Alveo card; in simulation (run.py) the same code drives the RTL.

On a card: `python test_pynq.py design.xclbin` with PYNQ's Alveo support (pynq.Overlay on an xclbin).
"""
import os
import sys

import numpy as np

SIM = "COCOTB_SYS_ARGV" in os.environ
if SIM:
    import cocotbpynq.xrt
    from cocotbpynq.xrt import Overlay, allocate
else:
    from pynq import Overlay, allocate


def main(xclbin):
    ol = Overlay(xclbin)
    n, k = 100, 1000
    src = allocate((n,), np.uint32, target=ol.HBM0)  # the banks the movers' pointers are connected to
    dst = allocate((n,), np.uint32, target=ol.HBM1)
    src[:] = np.arange(n, dtype=np.uint32) * 3
    dst[:] = 0xFFFFFFFF
    src.sync_to_device()
    dst.sync_to_device()
    ol.addk_1.write(0x10, k)  # ap_ctrl_none: registers only
    assert ol.addk_1.read(0x10) == k
    for rep in range(2):  # a kernel can be started again once it is done
        out = ol.s2mm_1.start(dst, n)
        ol.mm2s_1.call(src, n)
        out.wait()
        dst.sync_from_device()
        assert (dst == src + k).all(), f"run {rep}: {dst[:8]} != {(src + k)[:8]}"
    assert ol.addk_1.read(0x14) == 2 * n
    print(f"PASS: {n} words through mm2s_1 -> addk_1 (+{k}) -> s2mm_1, twice")


if SIM:
    @cocotbpynq.xrt.synctest
    def test_alveo(dut):
        main(os.environ["COCOTB_SYS_ARGV"])
elif __name__ == "__main__":
    main(sys.argv[1])
