# cocotbpynq
cocotbpynq is an extension of cocotb that lets PYNQ applications run in simulation. This makes it possible to debug AXI transactions between the programmable logic (PL) and processing system (PS) before deploying to hardware. The included example targets the PYNQ-Z1, and the same approach can be adapted to other PYNQ-compatible platforms.

## Installation
Install cocotbpynq from PyPI:

`pip install cocotbpynq`

Alternatively, install the latest version from this repository:

```sh
git clone https://github.com/watcag/cocotbpynq.git
cd cocotbpynq
python3 -m pip install .
```


## cocotbpynq.sample
### How to use cocotbpynq
The `src/cocotbpynq/sample` directory contains a complete example, including a hardware handoff file. Use `cocotb_runner.py` and `adapted.py` as references when developing your own tests.
### Running the sample
You can run this sample project mentioned above (after installing cocotbpynq) with:

`python3 -m cocotbpynq.sample`

The sample uses Verilator, which must be installed separately.
### Adaptation from PYNQ code
The `original.py` and `original_vs_adapted.diff` files illustrate the changes needed to make PYNQ code simulation-ready. The adapted application can be run either through `cocotb_runner.py` in simulation or on a compatible PYNQ board.
### Verilog Description
The sample has one AXI-Lite port (MMIO), one AXI-Stream input (DMA send), and one AXI-Stream output (DMA receive). The circuit computes `y = ax² + bx + c`. The constants `a`, `b`, and `c` can be read or modified through MMIO addresses `0x10`, `0x18`, and `0x20`; `x` and `y` are the streaming input and output.

### HWH Generation
The HWH file can be generated independently of the bitstream with this Vivado Tcl command:

`generate_target all <block design file>`

This avoids a full bitstream build. Regenerate the HWH file only when the block design changes.


## Acknowledgement
This work builds on [cocotb](https://github.com/cocotb/cocotb).

It also adapts concepts from [PYNQ](https://github.com/Xilinx/PYNQ), which was an important reference for this project.

## Paper
The paper, “Cocotb-Pynq: Co-simulating Python+RTL Applications Targeting Pynq Platforms with Cocotb,” was presented at the 35th International Conference on Field-Programmable Logic and Applications (FPL 2025). [Read the paper](https://nachiket.github.io/publications/cocotb-pynq_fpl-2025.pdf).
