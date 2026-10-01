import numpy as np
import sys

from pynq import Overlay
from pynq import MMIO
from pynq import allocate
from pynq import PL


def main(dut=None):
    IP_BASE_ADDRESS = 0x43C10000
    ADDRESS_RANGE = 0x1000
    PL.reset()  # Does nothing for cocotbpynq, no cache to reset
    # For cocotbpynq, path is prepended by BITSTREAM_OUTPUT_DIR env variable
    overlay = Overlay('./sample.bit')
    mmio = MMIO(IP_BASE_ADDRESS, ADDRESS_RANGE)

    a_val = 1
    b_val = 2
    c_val = 3

    # load constants
    mmio.write(0x10, a_val)  # load a
    mmio.write(0x18, b_val)  # load b
    mmio.write(0x20, c_val)  # load c

    assert (mmio.read(0x10) == a_val)
    assert (mmio.read(0x18) == b_val)
    assert (mmio.read(0x20) == c_val)

    # load inputs
    in_buffer = allocate(shape=(5,), dtype=np.uint32)
    out_buffer = allocate(shape=(5,), dtype=np.uint32)

    for i in range(0, len(in_buffer)):
        in_buffer[i] = 10+i

    overlay.poly_eval.axi_dma.recvchannel.transfer(out_buffer)
    overlay.poly_eval.axi_dma.sendchannel.transfer(in_buffer)
    overlay.poly_eval.axi_dma.sendchannel.wait()
    overlay.poly_eval.axi_dma.recvchannel.wait()

    expected_out = list(map(lambda x: a_val*x*x+b_val*x+c_val, in_buffer))
    assert (out_buffer == expected_out).all()
    print("\nAnswer:")
    print(out_buffer)


if __name__ == "__main__":
    main()
