# cocotbpynq
cocotbpynq is an extension of cocotb that lets PYNQ applications run in simulation. This makes it possible to debug AXI transactions between the programmable logic (PL) and processing system (PS) before deploying to hardware. The included example targets the PYNQ-Z1, and the same approach can be adapted to other PYNQ-compatible platforms.

It also contains a swap-aware partial-reconfiguration (PR) co-simulation engine, used by [pynq-pr](../pynq-pr/) to simulate reconfigurable-module swaps while the static design keeps running.

The API is not yet stable (0.x releases): minor versions may change it.

## Installation
cocotbpynq runs on the host (Linux or macOS), not on the PYNQ board. Releases are published on [GitHub Releases](https://github.com/watcag/cocotbpynq/releases); replace `0.2.0` with the release you want:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install "cocotbpynq==0.2.0" verilator --find-links https://github.com/watcag/cocotbpynq/releases/expanded_assets/v0.2.0
python -m cocotbpynq.sample          # should end with TESTS=1 PASS=1 FAIL=0
```

The `cocotbpynq` package on PyPI is still the old 0.0.3 (cocotb 1.x) and does not work with cocotb 2.x.

cocotbpynq needs Verilator 5.036 or newer, which Linux distribution packages (e.g. `apt`) do not provide yet. The `verilator` wheel from PyPI (installed above) works and cocotbpynq finds it automatically. Other options: `brew install verilator` (macOS) or the [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build) tarball.

To run the examples, work from a clone (see the [repository README](../../README.md)).

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

## Partial-reconfiguration simulation
`examples/cocotbpynq/` contains six PR designs (AXI-Lite, dual DMA, stream, AXI-Stream switch, matmul pipeline, video pipeline). Each one describes the static region and reconfigurable modules in `pr_config.yaml` and runs an unmodified PYNQ-style test (`test_pynq.py`) that calls `overlay.pr_download(...)` to swap modules mid-simulation:

```sh
git clone https://github.com/watcag/cocotbpynq.git && cd cocotbpynq
pip install "./packages/cocotbpynq[examples]" verilator
cd examples/cocotbpynq/axi_pr_example && python run.py
```

For the full Vivado DFX flow (block design, floorplanning, partial bitstreams, board runtime) from a single YAML file, see [pynq-pr](../pynq-pr/).

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
