"""
Minimal test: add, sub, mult individually via DMA.

Usage:
    Board:  python3 pr_min_test.py --project tutorial_z1
    Sim:    python3 run.py
"""
import os
import numpy as np

COCOTB_IS_RUNNING = "COCOTB_SYS_ARGV" in os.environ

if not COCOTB_IS_RUNNING:
    import argparse
    from pynq import allocate
    from overlay import Overlay
else:
    import cocotbpynq
    from pynq_pr.overlay_sim import Overlay, allocate

X = list(range(16))


def dma_test(dma):
    x_buf = allocate(shape=len(X), dtype=np.int32)
    y_buf = allocate(shape=len(X), dtype=np.int32)
    np.copyto(x_buf, np.array(X, dtype=np.int32))
    dma.recvchannel.transfer(y_buf)
    dma.sendchannel.transfer(x_buf)
    dma.sendchannel.wait()
    dma.recvchannel.wait()
    result = list(y_buf)
    return result


def main(dut=None):
    if COCOTB_IS_RUNNING:
        ol = Overlay('design.bit')
    else:
        parser = argparse.ArgumentParser(description="Minimal PR test")
        parser.add_argument("--project", required=True)
        parser.add_argument("--icap", action="store_true")
        args = parser.parse_args()
        ol = Overlay(f"{args.project}.bit")

    tests = [
        ("add",  "add_c_5",   lambda x: x + 5),
        ("sub",  "sub_c_3",   lambda x: x - 3),
        ("mult", "mult_c_10", lambda x: x * 10),
    ]

    for pname, bitname, fn in tests:
        ol.pr_download(pname, f"{bitname}.bit")
        dma = ol.chain([pname])
        result = dma_test(dma)
        exp = [fn(v) for v in X]
        status = "PASS" if result == exp else "FAIL"
        print(f"  {pname}/{bitname}: {result}  [{status}]")
        assert result == exp, f"{pname}/{bitname}: got {result}, expected {exp}"


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
