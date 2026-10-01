"""
Run on the PYNQ board after deploying bitstreams built with reconfiguration_method: icap.
Tests a 2-RP design: 'add' partition (poly_sum) and 'sub' partition (poly_sub).

Decoupling uses gpio_decouple where bit i controls RP i.
Each RP has its own DMA at <partition>.dma.
Reconfiguration is done via ICAP through the Versatile axi3_ctrl IP.

Usage:
    python3 pr_versatile_test.py --board z1 --project tutorial_z1
"""
import argparse

from pynq import allocate, Overlay, PL, MMIO
from pynq.lib import AxiGPIO
import numpy as np

PARTITIONS = [
    ("add", [("add_c_5", "x + 5"), ("add_c_10", "x + 10")]),
    ("sub", [("sub_c_3", "x - 3"), ("sub_c_7", "x - 7")]),
]

REG0_OFFSET = 0x00
REG1_OFFSET = 0x04
REG2_OFFSET = 0x08

START_BIT = (1 << 0)
PRG_BIT   = (1 << 1)
READY_BIT = (1 << 2)


class RM_ICAP:

    def __init__(self, binfile, mmio):
        self.mmio = mmio
        self.buffer = None
        self._preload(binfile)

    def _preload(self, binfile):
        print(f"  Preloading {binfile} into DRAM")
        with open(binfile, "rb") as f:
            bitstream = np.fromfile(f, dtype=np.uint32)
        padded = np.pad(bitstream, (250, 50), mode="constant")
        buf = allocate(shape=(len(padded),), dtype=np.uint32)
        buf[:] = padded
        size = len(padded)
        start_addr = buf.physical_address
        if size % 16 == 0:
            end_addr = start_addr + (32 * (size // 32 - 1) * 4)
            arlen = 15
        else:
            end_addr = start_addr + (32 * (size // 32) * 4)
            arlen = (size // 2) % 16 - 1
        self.start_addr = start_addr
        self.end_addr = end_addr
        self.burst = arlen
        self.buffer = buf

    def download(self):
        self.mmio.write(REG1_OFFSET, self.start_addr)
        self.mmio.write(REG2_OFFSET, self.end_addr)
        self.mmio.write(REG0_OFFSET, (self.burst << 2) | PRG_BIT)
        self.mmio.write(REG0_OFFSET, START_BIT)
        self.mmio.write(REG0_OFFSET, 0x00)
        while not (self.mmio.read(REG0_OFFSET) & READY_BIT):
            continue

    def __del__(self):
        if self.buffer is not None:
            self.buffer.freebuffer()


def test(dma):
    x = list(range(16))
    x_buf = allocate(shape=len(x), dtype=np.int32)
    y_buf = allocate(shape=len(x), dtype=np.int32)
    np.copyto(x_buf, np.array(x))
    dma.recvchannel.transfer(y_buf)
    dma.sendchannel.transfer(x_buf)
    dma.sendchannel.wait()
    dma.recvchannel.wait()
    print(list(y_buf))
    x_buf.freebuffer()
    y_buf.freebuffer()


def reconfigure(rm, decoupler, bit_index):
    mask = 1 << bit_index
    decoupler.write(mask, mask)
    rm.download()
    decoupler.write(0, mask)


def main():
    parser = argparse.ArgumentParser(description="Add/Sub ICAP PR test on PYNQ board")
    parser.add_argument("--board", default="z1", choices=["z1", "kv260"])
    parser.add_argument("--project", default=None)
    args = parser.parse_args()

    project = args.project or f"tutorial_{args.board}"

    PL.reset()
    print(f"Loading static bitstream: {project}.bit")
    overlay = Overlay(f"{project}.bit")

    ctrl_info = overlay.ip_dict["versatile/axi3_ctrl_0"]
    mmio = MMIO(ctrl_info["phys_addr"], ctrl_info["addr_range"])
    decoupler = AxiGPIO(overlay.ip_dict["gpio_decouple"]).channel1

    modules = {}
    for pname, mods in PARTITIONS:
        for bitname, _ in mods:
            modules[bitname] = RM_ICAP(f"{bitname}.bin", mmio)

    for i, (pname, mods) in enumerate(PARTITIONS):
        dma = getattr(overlay, pname).dma
        for bitname, desc in mods:
            print(f"Reconfiguring {pname} -> {bitname}  ({desc})")
            reconfigure(modules[bitname], decoupler, i)
            print("  Result: ", end="")
            test(dma)


if __name__ == "__main__":
    main()
