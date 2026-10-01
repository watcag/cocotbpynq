"""
Run on hardware or in cocotbpynq simulation.
Tests independent RP reconfiguration and chained pipelines via axis_switch.

Usage:
    Board:  python3 pr_test.py --project tutorial_z1
    Board:  python3 pr_test.py --project tutorial_z1 --icap
    Sim:    pynq-pr sim -c pr_z1.yaml --test pr_test.py -f
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

PARTITIONS = {
    "add":  [("add_c_5",   lambda x: x + 5),  ("add_c_10", lambda x: x + 10)],
    "sub":  [("sub_c_3",   lambda x: x - 3),  ("sub_c_7",  lambda x: x - 7)],
    "mult": [("mult_c_10", lambda x: x * 10)],
}

X = list(range(16))


def gen_chains():
    """Generate all pairwise permutations using the first module of each partition."""
    from itertools import permutations
    items = [(p, mods[0][0], mods[0][1]) for p, mods in PARTITIONS.items()]
    chains = []
    for r in range(2, len(items) + 1):
        for perm in permutations(items, r):
            chains.append([(p, name, fn) for p, name, fn in perm])
    return chains


def expected(chain):
    result = list(X)
    for _, _, fn in chain:
        result = [fn(v) for v in result]
    return result


def dma_test(send_dma, recv_dma=None):
    if recv_dma is None:
        recv_dma = send_dma
    x_buf = allocate(shape=len(X), dtype=np.int32)
    y_buf = allocate(shape=len(X), dtype=np.int32)
    np.copyto(x_buf, np.array(X, dtype=np.int32))
    recv_dma.recvchannel.transfer(y_buf)
    send_dma.sendchannel.transfer(x_buf)
    send_dma.sendchannel.wait()
    recv_dma.recvchannel.wait()
    result = list(y_buf)
    if hasattr(x_buf, "freebuffer"):
        x_buf.freebuffer()
    if hasattr(y_buf, "freebuffer"):
        y_buf.freebuffer()
    return result


FAILURES = []


def test_independent(ol, icap):
    print("\n=== Independent ===")
    ext = ".bin" if icap else ".bit"
    for pname, modules in PARTITIONS.items():
        for bitname, fn in modules:
            ol.pr_download(pname, f"{bitname}{ext}", icap=icap)
            if getattr(ol, "_switch", None) is not None:
                dma = ol.chain([pname])
            else:
                dma = getattr(ol, pname).dma
            result = dma_test(dma)
            exp = [fn(v) for v in X]
            status = "PASS" if result == exp else "FAIL"
            print(f"  {pname}/{bitname}: {result}  [{status}]")
            if status == "FAIL":
                FAILURES.append(f"{pname}/{bitname}")


def test_chains(ol, icap):
    if ol._switch is None:
        print("\n=== Skipping chain tests (no axis_switch) ===")
        return

    print("\n=== Chains ===")
    ext = ".bin" if icap else ".bit"
    for chain in gen_chains():
        label = " -> ".join(f"{p}/{m}" for p, m, _ in chain)

        for partition, module, _ in chain:
            ol.pr_download(partition, f"{module}{ext}", icap=icap)

        dma = ol.chain([p for p, _, _ in chain])
        result = dma_test(dma)
        exp = expected(chain)
        status = "PASS" if result == exp else "FAIL"
        print(f"  {label}: {result}  [{status}]")
        if status == "FAIL":
            FAILURES.append(label)

    ol.default_routing()


def main(dut=None):
    if COCOTB_IS_RUNNING:
        ol = Overlay("design.bit")
        icap = False
    else:
        parser = argparse.ArgumentParser(description="PrOverlay test")
        parser.add_argument("--project", required=True)
        parser.add_argument("--icap", action="store_true",
                            help="Use ICAP (.bin) instead of PCAP (.bit)")
        args = parser.parse_args()
        ol = Overlay(f"{args.project}.bit")
        icap = args.icap

    test_independent(ol, icap)
    test_chains(ol, icap)

    print("\nAll tests done.")
    assert not FAILURES, f"{len(FAILURES)} mismatches: {FAILURES}"


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
