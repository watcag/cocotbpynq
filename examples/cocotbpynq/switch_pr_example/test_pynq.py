"""
AXI-Stream Switch PR example — tests runtime pipeline routing.

Same test code runs on PYNQ board (with pynq-pr) and in cocotbpynq simulation.
The switch enables dynamic chaining of partitions at runtime:
  default:  each DMA ↔ its own RM independently
  chain():  DMA₀ → RM₀ → RM₁ → … → RMₙ → DMA₀

Switch port mapping (matching pynq-pr convention):
  SI/MI 2*i   = RP[i] (partition FSM ↔ DPI bridge)
  SI/MI 2*i+1 = DMA[i]
"""
import os
import numpy as np

COCOTB_IS_RUNNING = "COCOTB_SYS_ARGV" in os.environ

if not COCOTB_IS_RUNNING:
    from pynq import Overlay, allocate
else:
    import cocotbpynq
    from cocotbpynq import Overlay, allocate, MMIO

# ── Switch control constants (Xilinx PG085 register map) ──────────────
SWITCH_ADDR      = 0x44A00000
SWITCH_RANGE     = 0x10000
MI_MUX_BASE      = 0x40
CTRL_REG         = 0x00
COMMIT           = 0x2
DISABLE          = 0x80000000

# Partition name → index (matches YAML partition order)
PARTITIONS = {"rp_add": 0, "rp_sub": 1, "rp_mult": 2}
NUM_PORTS  = 6   # 2 * len(PARTITIONS)


def switch_route(sw, mapping):
    """Program switch and commit.  mapping = {master_idx: slave_idx}."""
    for mi in range(NUM_PORTS):
        si = mapping.get(mi, DISABLE)
        sw.write(MI_MUX_BASE + 4 * mi, si)
    sw.write(CTRL_REG, COMMIT)


def switch_default(sw):
    """1:1 DMA ↔ RP routing."""
    m = {}
    for i in range(NUM_PORTS // 2):
        m[2 * i]     = 2 * i + 1   # RP input ← its DMA
        m[2 * i + 1] = 2 * i       # DMA S2MM ← RP output
    switch_route(sw, m)


def switch_chain(sw, names):
    """Pipeline: DMA₀ → names[0] → names[1] → … → DMA₀."""
    idx = [PARTITIONS[n] for n in names]
    m = {}
    m[2 * idx[0]] = 2 * idx[0] + 1                     # first RP ← its DMA
    for k in range(len(idx) - 1):
        m[2 * idx[k + 1]] = 2 * idx[k]                 # next RP ← prev RP
    m[2 * idx[0] + 1] = 2 * idx[-1]                    # first DMA ← last RP
    switch_route(sw, m)


def stream(dma, x, y):
    """Send x through DMA, receive into y."""
    dma.sendchannel.transfer(x)
    dma.recvchannel.transfer(y)
    dma.sendchannel.wait()
    dma.recvchannel.wait()


def check(label, got, expected):
    got_arr = np.array(got, dtype=np.int32)
    exp_arr = np.array(expected, dtype=np.int32)
    if not np.array_equal(got_arr, exp_arr):
        raise AssertionError(f"{label}: expected {exp_arr}, got {got_arr}")
    print(f"  PASS {label}: {got_arr}")


def main(dut=None):
    overlay = Overlay("design.bit")
    sw = MMIO(SWITCH_ADDR, SWITCH_RANGE)

    dma0 = overlay.axi_dma_0   # add
    dma1 = overlay.axi_dma_1   # sub
    dma2 = overlay.axi_dma_2   # mult

    x = allocate(shape=(6,), dtype=np.int32)
    y = allocate(shape=(6,), dtype=np.int32)
    x[:] = np.arange(1, 7, dtype=np.int32)   # [1,2,3,4,5,6]

    # ── Test 1: default routing — each RM independently ───────────────
    print("Test 1: default routing (1:1 DMA ↔ RP)")
    switch_default(sw)

    stream(dma0, x, y)
    check("add  (x+5)", y, x + 5)              # [6,7,8,9,10,11]

    stream(dma1, x, y)
    check("sub  (x-3)", y, x - 3)              # [-2,-1,0,1,2,3]

    stream(dma2, x, y)
    check("mult (x*10)", y, x * 10)            # [10,20,30,40,50,60]

    # ── Test 2: chain add → sub ───────────────────────────────────────
    print("Test 2: chain [add, sub]  → y = (x+5)-3 = x+2")
    switch_chain(sw, ["rp_add", "rp_sub"])

    stream(dma0, x, y)
    check("add→sub", y, x + 2)                 # [3,4,5,6,7,8]

    # ── Test 3: chain add → sub → mult ───────────────────────────────
    print("Test 3: chain [add, sub, mult]  → y = (x+2)*10")
    switch_chain(sw, ["rp_add", "rp_sub", "rp_mult"])

    stream(dma0, x, y)
    check("add→sub→mult", y, (x + 2) * 10)    # [30,40,50,60,70,80]

    # ── Test 4: different chain order ─────────────────────────────────
    print("Test 4: chain [rp_mult, rp_add]  → y = (x*10)+5")
    switch_chain(sw, ["rp_mult", "rp_add"])

    stream(dma2, x, y)                          # use mult's DMA as first
    check("mult→add", y, x * 10 + 5)           # [15,25,35,45,55,65]

    # ── Test 5: overlay.chain() API (matches pynq-pr) ───────────
    print("Test 5: overlay.chain() API  → y = (x+5)-3 = x+2")
    dma_chain = overlay.chain(["rp_add", "rp_sub"])
    stream(dma_chain, x, y)
    check("overlay.chain(add→sub)", y, x + 2)

    print("\nAll switch tests passed!")


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
