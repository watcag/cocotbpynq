"""
AXI PR example -- cocotbpynq integration test.

This file runs UNCHANGED on:
  - A real PYNQ board  (import pynq; python test_pynq.py)
  - Simulation        (via run.py  -> PRCocotbRunner)

Test flow:
  1. Write 0x1234 to data_in register (offset 0x00).
  2. Read result register (offset 0x04).
     adder_rm computes  result = data_in + 0x1000 -> expect 0x2234.
  3. Reconfigure rp_compute -> inverter_rm.
  4. Write 0x1234 again.
  5. Read result.
     inverter_rm computes  result = ~data_in -> expect 0xFFFF_EDCB.
"""
import os

COCOTB_IS_RUNNING = "COCOTB_SYS_ARGV" in os.environ

if not COCOTB_IS_RUNNING:
    from pynq import Overlay, MMIO
else:
    import cocotbpynq
    from cocotbpynq import Overlay, MMIO

IP_BASE  = 0x43C00000
IP_RANGE = 0x10000

DATA_IN_OFFSET = 0x00
RESULT_OFFSET  = 0x04


def main(dut=None):
    overlay = Overlay('design.bit')
    mmio    = MMIO(IP_BASE, IP_RANGE)

    # -- Test 1: adder_rm (result = data_in + 0x1000) -------------------------
    mmio.write(DATA_IN_OFFSET, 0x1234)
    assert mmio.read(DATA_IN_OFFSET) == 0x1234, "data_in read-back failed"
    mmio.read(RESULT_OFFSET)  # pipeline flush
    result = mmio.read(RESULT_OFFSET)
    expected = (0x1234 + 0x1000) & 0xFFFF_FFFF
    assert result == expected, \
        f"adder_rm: expected {expected:#010x}, got {result:#010x}"
    print(f"[PASS] adder_rm: 0x1234 + 0x1000 = {result:#010x}")

    # -- Reconfigure to inverter_rm --------------------------------------------
    print("Reconfiguring rp_compute: adder_rm -> inverter_rm ...")
    overlay.pr_download('rp_compute', 'inverter_rm')
    print("Reconfiguration complete.")

    # -- Test 2: inverter_rm (result = ~data_in) -------------------------------
    mmio.write(DATA_IN_OFFSET, 0x1234)
    assert mmio.read(DATA_IN_OFFSET) == 0x1234, "data_in read-back failed"
    mmio.read(RESULT_OFFSET)  # pipeline flush
    result = mmio.read(RESULT_OFFSET)
    expected = (~0x1234) & 0xFFFF_FFFF
    assert result == expected, \
        f"inverter_rm: expected {expected:#010x}, got {result:#010x}"
    print(f"[PASS] inverter_rm: ~0x1234 = {result:#010x}")

    # -- Reconfigure back to adder_rm ------------------------------------------
    print("Reconfiguring rp_compute: inverter_rm -> adder_rm ...")
    overlay.pr_download('rp_compute', 'adder_rm')
    print("Reconfiguration complete.")

    # -- Test 3: adder_rm again (verify round-trip) ----------------------------
    mmio.write(DATA_IN_OFFSET, 0xABCD)
    assert mmio.read(DATA_IN_OFFSET) == 0xABCD, "data_in read-back failed"
    mmio.read(RESULT_OFFSET)  # pipeline flush
    result = mmio.read(RESULT_OFFSET)
    expected = (0xABCD + 0x1000) & 0xFFFF_FFFF
    assert result == expected, \
        f"adder_rm (round-trip): expected {expected:#010x}, got {result:#010x}"
    print(f"[PASS] adder_rm round-trip: 0xABCD + 0x1000 = {result:#010x}")

    print("\n[PASS] All tests passed.")


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
