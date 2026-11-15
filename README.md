# cocotbpynq
cocotbpynq is an extension of cocotb that lets PYNQ applications run in simulation. This makes it possible to debug AXI transactions between the programmable logic (PL) and processing system (PS) before deploying to hardware. The included example targets the PYNQ-Z1, and the same approach can be adapted to other PYNQ-compatible platforms.

It also contains a swap-aware partial-reconfiguration (PR) co-simulation engine, used by [pynq-pr](https://github.com/watcag/pynq-pr) to simulate reconfigurable-module swaps while the static design keeps running.

The API is not yet stable (0.x releases): minor versions may change it.

## Installation
cocotbpynq runs on the host (Linux or macOS), not on the PYNQ board. Releases are published on GitHub: install a release tag (see [Releases](https://github.com/watcag/cocotbpynq/releases) for the latest).

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install "cocotbpynq @ git+https://github.com/watcag/cocotbpynq@v0.1.0" verilator
python -m cocotbpynq.sample          # should end with TESTS=1 PASS=1 FAIL=0
```

Note: the `cocotbpynq` package on PyPI is still the old 0.0.3 (cocotb 1.x) and does not work with cocotb 2.x; do not `pip install cocotbpynq` from PyPI until a newer release appears there.

cocotbpynq needs Verilator 5.036 or newer, which Linux distribution packages (e.g. `apt`) do not provide yet. The `verilator` wheel from PyPI (installed above) works and cocotbpynq finds it automatically. Other options: `brew install verilator` (macOS) or the [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build) tarball.

To work from a clone (e.g. to run the examples):

```sh
git clone https://github.com/watcag/cocotbpynq.git
cd cocotbpynq
git checkout v0.1.0                  # or stay on main for the latest development state
python3 -m pip install ".[examples]" verilator
```

To update, run the same `pip install` command with the newer release tag.

### Requirements
| | Supported | Tested |
|---|---|---|
| Python | 3.10+ | 3.10, 3.12, 3.14 |
| cocotb | 2.x | 2.0.1, 2.1.0 |
| Verilator | 5.036+ | 5.048 (PyPI wheel) |

## cocotbpynq.sample
### How to use cocotbpynq
The `src/cocotbpynq/sample` directory contains a complete example, including a hardware handoff file. Use `cocotb_runner.py` and `adapted.py` as references when developing your own tests.
### Running the sample
You can run this sample project mentioned above (after installing cocotbpynq) with:

`python -m cocotbpynq.sample`

Build files and results go to `./sim_build`, and the command exits non-zero if the test fails. The `SIM` environment variable selects another cocotb simulator (e.g. `SIM=icarus`; only Verilator is tested in CI).
### Adaptation from PYNQ code
The `original.py` and `original_vs_adapted.diff` files illustrate the changes needed to make PYNQ code simulation-ready. The adapted application can be run either through `cocotb_runner.py` in simulation or on a compatible PYNQ board.
### Verilog Description
The sample has one AXI-Lite port (MMIO), one AXI-Stream input (DMA send), and one AXI-Stream output (DMA receive). The circuit computes `y = ax² + bx + c`. The constants `a`, `b`, and `c` can be read or modified through MMIO addresses `0x10`, `0x18`, and `0x20`; `x` and `y` are the streaming input and output.

### HWH Generation
The HWH file can be generated independently of the bitstream with this Vivado Tcl command:

`generate_target all <block design file>`

This avoids a full bitstream build. Regenerate the HWH file only when the block design changes.

## PL masters reading and writing PS DDR (HP ports)
An RTL AXI4 master port (an accelerator that fetches its own data, e.g. through `S_AXI_HP0_FPD`) reads and writes the
buffers from `allocate` directly. `Overlay` attaches a slave port model (`cocotbpynq.axi_mem`) to every AXI4 master bus
interface of the DUT in the HWH; Zynq-7000 (`processing_system7`) and Zynq UltraScale+ (`zynq_ultra_ps_e`, e.g. KV260)
block designs both work, and `Overlay.ip_dict` lists the PS address map as PYNQ does.

* **Cache semantics.** A cacheable buffer has a CPU view (the array) and a device view (DRAM). The PL sees host writes
  only after `flush()` / `sync_to_device()`, and the host sees PL writes only after `invalidate()` /
  `sync_from_device()`, so a missing flush or invalidate shows the same stale data as on the board.
  `set_cache_model("strict")` (or `COCOTBPYNQ_CACHE=strict`) gives non-cacheable buffers the same split, to check a
  driver that relies on non-cacheable memory. `device_memory.stale_reads` counts PL reads of unflushed bytes.
* **HP-port timing** (`HpPortConfig`): outstanding read / write limits (8 each, the AFI reset value), read and write
  response latency with a random extra per burst, ARREADY / AWREADY / WREADY back-pressure, gaps between read beats,
  write data before its address, reordering of read bursts and write responses across IDs, and stalls that freeze a
  port for a random number of cycles. Set it with `cocotbpynq.axi_mem.default_config` / `port_configs` before the
  `Overlay`, or with `COCOTBPYNQ_HP="r_jitter=200,reorder=1"` (`COCOTBPYNQ_HP_<PORT>` for one port, by DUT interface or
  PS port name); `COCOTBPYNQ_AXI_SEED` seeds the random timing. On Zynq UltraScale+, PYNQ code that writes the AFI FM
  RDISSUE / WRISSUE registers (`MMIO(0xFD380000, 0x20).write(0x04, n - 1)`) sets the matching port's limit, as on the board.
* **Checks.** The master's AXI protocol errors (VALID dropped before READY, payload changed while waiting, WLAST on the
  wrong beat, a burst over a 4 KB boundary, an address outside every buffer) are kept in `axi_mem.memory.errors`;
  `axi_mem.memory.outstanding()` and `idle()` tell what is in flight, `stats()` counts bursts, beats and stalls.
* **Host timing.** `cocotbpynq.host` adds idle cycles before MMIO accesses (`mmio_cycles`, and `write_delay` per
  register offset, e.g. a gap before a start bit), or advances the simulation by the real time the host code took
  between accesses (`compute = "wall"`). `cocotbpynq.simtime` is a stand-in for the `time` module in simulated
  seconds, so host timeouts and timings follow the DUT clock. `Clocks` and `Interrupt` stand in for PYNQ's.
* A DUT with several clock ports (e.g. a 2x array clock) gets every clock at its HWH frequency ratio, edges aligned.

`examples/axi_master_example` is a small AXI4 memcpy engine on a Zynq UltraScale+ HWH, driven by unmodified PYNQ code
(`test_pynq.py`): a copy with flush and invalidate, one without the flush and one without the invalidate.

```sh
cd examples/axi_master_example && python run.py          # the HP port's reset timing
python run.py stress                                     # random latency, back-pressure, gaps, stalls, reordering
pytest tests/test_axi_mem.py                             # from the repository root
```

## Partial-reconfiguration simulation
`examples/*_pr_example` contains six PR designs (AXI-Lite, dual DMA, stream, AXI-Stream switch, matmul pipeline, video pipeline). Each one describes the static region and reconfigurable modules in `pr_config.yaml` and runs an unmodified PYNQ-style test (`test_pynq.py`) that calls `overlay.pr_download(...)` to swap modules mid-simulation:

```sh
git clone https://github.com/watcag/cocotbpynq.git && cd cocotbpynq
pip install ".[examples]" verilator
cd examples/axi_pr_example && python run.py
```

For the full Vivado DFX flow (block design, floorplanning, partial bitstreams, board runtime) from a single YAML file, see [pynq-pr](https://github.com/watcag/pynq-pr).

An RM can run on the Vivado simulator instead of Verilator: `simulator: xsim` in its entry of
`reconfigurable_modules`. Its sources are compiled with `xvlog`/`xelab -dll` (with Vivado's
`unisims_ver` and `secureip`) and driven through XSI by a generated RM driver, under the same static
region and test. This is how a Vivado netlist of an RM (`write_verilog -mode funcsim`) runs with
Vivado's own primitive models. It needs Vivado 2024.1 or newer (`libxv_simulator_kernel.so`) with its
`settings64.sh` sourced. For a large netlist on Verilator, `verilator_public: false` leaves out
`--public-flat-rw`, which otherwise keeps every net from being optimised.

`PRCocotbRunner(merge_waveforms=True)` is experimental and requires the unreleased `ewal` waveform tool; it is off by default.

## Versions and reproducing the papers
| Version | Paper | Install |
|---|---|---|
| `0.0.3` | FPL 2025 (Cocotb-Pynq) | `pip install "cocotbpynq==0.0.3" "cocotb<2"`. The "Write Error occured. Response: 0b0" messages it prints are a known cosmetic bug, fixed in 0.1.0. |
| `0.1.0` | FPL 2026 (Cocotb-PYNQ-PR), with pynq-pr `0.1.1` | `pip install "cocotbpynq @ git+https://github.com/watcag/cocotbpynq@v0.1.0"` |

This repository contains the tools and examples. The papers' benchmark harnesses, raw measurements and hardware designs are not included.

## Acknowledgement
This work builds on [cocotb](https://github.com/cocotb/cocotb).

It also adapts concepts from [PYNQ](https://github.com/Xilinx/PYNQ), which was an important reference for this project.

## Papers
If you use cocotbpynq, please cite the papers below (see also `CITATION.cff`).

- “Cocotb-Pynq: Co-simulating Python+RTL Applications Targeting Pynq Platforms with Cocotb,” G. Lusby and N. Kapre, 35th International Conference on Field-Programmable Logic and Applications (FPL 2025). [Read the paper](https://nachiket.github.io/publications/cocotb-pynq_fpl-2025.pdf).
- “Cocotb-PYNQ-PR: From Co-Simulation to Deployment, A Unified DFX Framework for PYNQ,” E. Guevara, C. Sharma, G. Lusby and N. Kapre, FPL 2026. [Read the paper](https://nachiket.github.io/publications/cocotb-pynq-pr_fpl-2026.pdf).
