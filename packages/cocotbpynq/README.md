# cocotbpynq
cocotbpynq is an extension of cocotb that lets PYNQ applications run in simulation. This makes it possible to debug AXI transactions between the programmable logic (PL) and processing system (PS) before deploying to hardware. The included example targets the PYNQ-Z1, and the same approach can be adapted to other PYNQ-compatible platforms.

It also contains a swap-aware partial-reconfiguration (PR) co-simulation engine, used by [pynq-pr](https://github.com/watcag/cocotbpynq/tree/main/packages/pynq-pr) to simulate reconfigurable-module swaps while the static design keeps running.

The API is not yet stable (0.x releases): minor versions may change it.

## Installation
cocotbpynq runs on the host (Linux or macOS), not on the PYNQ board. Install it from PyPI:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install cocotbpynq verilator
python -m cocotbpynq.sample          # should end with TESTS=1 PASS=1 FAIL=0
```

cocotbpynq needs Verilator 5.036 or newer, which Linux distribution packages (e.g. `apt`) do not provide yet. The `verilator` wheel from PyPI (installed above) works and cocotbpynq finds it automatically. Other options: `brew install verilator` (macOS) or the [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build) tarball.

To run the examples, work from a clone (see the [repository README](https://github.com/watcag/cocotbpynq#readme)).

### Requirements
| | Supported | Tested |
|---|---|---|
| Python | 3.10+ | 3.10, 3.12, 3.14 |
| cocotb | 2.x | 2.0.1, 2.1.0 |
| Verilator | 5.036+ | 5.048 (PyPI wheel) |

## cocotbpynq.sample
### How to use cocotbpynq
The `packages/cocotbpynq/src/cocotbpynq/sample` directory contains a complete example, including a hardware handoff file. Use `cocotb_runner.py` and `adapted.py` as references when developing your own tests.
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

### Simulated PYNQ release (embedded boards)
The simulated board behaves as PYNQ 4.0.0 by default. Environment variables choose what it runs:

| Variable | Default | Effect |
|---|---|---|
| `COCOTBPYNQ_PYNQ_VERSION` | `4.0.0` | `3.0.1` for PYNQ 3 behaviour (e.g. PYNQ-Z1/Z2, which PYNQ 4 does not support). |
| `COCOTBPYNQ_PYXRT` | `2.13.479` | XRT version of the board's pyxrt. Before 2.16, pyxrt has no `bo.sync(direction)`, so PYNQ 4's `flush()`/`invalidate()` raise as on such a board; give `2.16` or later for an image with a newer XRT. |
| `COCOTBPYNQ_DEVICE_TREE` | unset (configured board) | A directory standing for `/proc/device-tree`; without `chosen/pynq_board`, PYNQ 4 is off target and opening the device raises `NameError` for `pyxrt`. |

Under PYNQ 4, each full or partial load writes `loaded.xclbin` into the current directory, buffers are at
least 8 KiB, and a slice's `flush()`/`invalidate()` syncs the whole buffer. Host code that works around an
old pyxrt with `buf.bo.sync(direction, size, offset)` runs unchanged against `cocotbpynq.pyxrt`.

## Alveo cards (XRT)
`cocotbpynq.xrt` runs PYNQ host code written for an Alveo card against the RTL of the design's compute units (CUs). The host code changes only its imports, as in the sample:

```python
if "COCOTB_SYS_ARGV" in os.environ:          # in simulation
    from cocotbpynq.xrt import Overlay, allocate
else:                                         # on the card
    from pynq import Overlay, allocate

ol = Overlay("design.xclbin")
src = allocate((n,), np.uint32, target=ol.HBM0)   # the bank the kernel argument is connected to
src.sync_to_device()
ol.mm2s_1.call(src, n)                       # ap_ctrl_hs / ap_ctrl_chain: arguments, AP_START, wait for AP_IDLE
ol.addk_1.write(0x10, k)                     # any CU's registers, including ap_ctrl_none kernels
```

- `make_top(xclbin, sources, out)` writes the simulation top from the xclbin's metadata: one instance per CU (the module named after its kernel), the AXI4-Stream connections (`--connectivity.sc`) wired, `ap_clk`/`ap_rst_n` shared, and every CU's control and AXI4 master ports brought out as `<cu>_<port>_<SIGNAL>`.
- `Overlay(xclbin)` reads the same metadata: it serves every AXI4 master from a model of the card's memory banks (HBM pseudo-channels, DDR, PLRAM, at their device addresses) and drives each CU's AXI-Lite control port. `ol.<cu>` and `ol.<bank>` (`HBM[0]` is `ol.HBM0`, as in PYNQ), `ol.ip_dict` and `ol.mem_dict` follow PYNQ.
- `allocate` returns host buffers in a bank. As on the card, `sync_to_device()` and `sync_from_device()` copy them to and from the bank, so a missing sync shows up in simulation.
- Kernels are started through their registers, as PYNQ's register start path does: arguments, then AP_START; `wait()` polls AP_IDLE and writes AP_CONTINUE for `ap_ctrl_chain` kernels.
- Only the xclbin's metadata is read, so an xclbin built for any target works. `write_xclbin(path, xml, mems, connections)` writes a metadata-only xclbin, to simulate a design before it is linked.

`examples/cocotbpynq/alveo_example` has three CUs (a memory-to-stream mover, an `ap_ctrl_none` stream kernel and a stream-to-memory mover) on two HBM pseudo-channels:

```sh
cd examples/cocotbpynq/alveo_example && python run.py
```

On a card, PYNQ 3.0.1 is the last release that drives Alveo cards (3.1 deprecated them). Its XRT backend binds XRT's `xcl*` C functions, which recent XRT releases (2.23 checked) no longer export, so newer XRT needs a port of `pynq.pl_server.xrt_device` to the XRT native API (`xrt::bo`, `xrt::ip`): [watcag/PYNQ `xrt-native`](https://github.com/watcag/PYNQ/tree/xrt-native), `pip install "git+https://github.com/watcag/PYNQ@xrt-native"`. Only Verilator is tested.

## Partial-reconfiguration simulation
`examples/cocotbpynq/` contains six PR designs (AXI-Lite, dual DMA, stream, AXI-Stream switch, matmul pipeline, video pipeline). Each one describes the static region and reconfigurable modules in `pr_config.yaml` and runs an unmodified PYNQ-style test (`test_pynq.py`) that calls `overlay.pr_download(...)` to swap modules mid-simulation:

```sh
git clone https://github.com/watcag/cocotbpynq.git && cd cocotbpynq
pip install "./packages/cocotbpynq[examples]" verilator
cd examples/cocotbpynq/axi_pr_example && python run.py
```

For the full Vivado DFX flow (block design, floorplanning, partial bitstreams, board runtime) from a single YAML file, see [pynq-pr](https://github.com/watcag/cocotbpynq/tree/main/packages/pynq-pr).

A partition whose RM has AXI-Stream pairs `x`/`y`, `x1`/`y1`, ... can have one DMA per pair: give each
DMA's `sb` interfaces `partition: <name>`, and the partition's k-th DMA (in interface order) drives `x<k>`/`y<k>`.

### Netlist co-simulation
An RM can be simulated from its Vivado netlist instead of its RTL, under the same static region and host
test. This catches synthesis or implementation that changes what the RM computes, which RTL simulation
cannot. Export the netlist with `write_verilog -mode funcsim`, from the routed design (the RM's cell) or
from the RM's own synthesis checkpoint (its top):

```tcl
open_checkpoint top_routed.dcp
write_verilog -mode funcsim -force -cell [get_cells <RM cell>] rm_funcsim.v
```

and point the RM's entry in `reconfigurable_modules` at it (`design` is the netlist's top module). Two
simulators can run it:

- **Vivado simulator** (Vivado's own UNISIM and SecureIP models), from the Vivado that builds the design
  (e.g. 2022.2 for PYNQ 3.0, 2024.x for PYNQ 3.1) with `settings64.sh` sourced. The RM is built with
  `xvlog`/`xelab -dll` and driven through XSI:

  ```yaml
  - name: my_rm_netlist
    partition: rp0
    design: my_rm
    sources: [rm_funcsim.v]
    simulator: xsim
  ```

- **Verilator**, with the Verilator-compatible primitive models of
  [verilator-unisims](https://github.com/watcag/verilator-unisims)
  (`git clone https://github.com/watcag/verilator-unisims`). `-DGLBL` skips the netlist's own
  `glbl`, and `verilator_public: false` leaves out `--public-flat-rw`, which would keep every net of a
  large netlist out of the optimiser:

  ```yaml
  - name: my_rm_netlist
    partition: rp0
    design: my_rm
    sources: [rm_funcsim.v]
    verilator_public: false
    verilator_flags: [-y, /path/to/verilator-unisims, -DGLBL, --no-timing, -Wno-fatal, -Wno-lint, -Wno-style,
                      -O3, --output-split-cfuncs, "2000"]
  ```

  The models must cover every primitive in the netlist.

Both run at the same cycle level as the RTL RM. Verilator is about 100 times faster once built; xsim
needs no extra models. Neither simulates timing: the netlist is functional (funcsim), so a design that
fails timing can still pass.

`PRCocotbRunner(merge_waveforms=True)` is experimental and requires the unreleased `ewal` waveform tool; it is off by default.

## Versions and reproducing the papers
| Version | Paper | Install |
|---|---|---|
| `0.0.3` | FPL 2025 (Cocotb-Pynq) | `pip install "cocotbpynq==0.0.3" "cocotb<2"`. The "Write Error occured. Response: 0b0" messages it prints are a known cosmetic bug, fixed in 0.1.0. |
| `0.1.0` | FPL 2026 (Cocotb-PYNQ-PR), with pynq-pr `0.1.1` | `pip install "cocotbpynq @ git+https://github.com/watcag/cocotbpynq@v0.1.0"` (pynq-pr 0.1.1: [watcag/pynq-pr](https://github.com/watcag/pynq-pr) tag `v0.1.1`) |

This repository contains the tools and examples. The papers' benchmark harnesses, raw measurements and hardware designs are not included.

## Acknowledgement
This work builds on [cocotb](https://github.com/cocotb/cocotb).

It also adapts concepts from [PYNQ](https://github.com/Xilinx/PYNQ), which was an important reference for this project.

## Papers
If you use cocotbpynq, please cite the papers below (see also `CITATION.cff`).

- “Cocotb-Pynq: Co-simulating Python+RTL Applications Targeting Pynq Platforms with Cocotb,” G. Lusby and N. Kapre, 35th International Conference on Field-Programmable Logic and Applications (FPL 2025). [Read the paper](https://nachiket.github.io/publications/cocotb-pynq_fpl-2025.pdf).
- “Cocotb-PYNQ-PR: From Co-Simulation to Deployment, A Unified DFX Framework for PYNQ,” E. Guevara, C. Sharma, G. Lusby and N. Kapre, FPL 2026. [Read the paper](https://nachiket.github.io/publications/cocotb-pynq-pr_fpl-2026.pdf).
