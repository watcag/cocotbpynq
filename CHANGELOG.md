# Changelog

Both packages (cocotbpynq and pynq-pr) are released together under one version from 0.2.0 onwards.

## Unreleased

### Added
- `cocotbpynq.xrt`: PYNQ host code for Alveo cards (`Overlay("design.xclbin")`, `allocate(..., target=ol.HBM0)`,
  `ol.<cu>.call/start/read/write`) runs against the RTL of the design's compute units. `make_top` writes the
  simulation top from the xclbin's metadata (AXI4-Stream connections wired, control and AXI4 master ports
  brought out); the overlay serves AXI4 masters from a model of the card's memory banks and drives each CU's
  AXI-Lite control port. `write_xclbin` writes a metadata-only xclbin to simulate before linking. Example:
  `examples/cocotbpynq/alveo_example`.
- pynq-pr: Alinx VD100 board (Versal AI Edge `xcve2302`, Vivado 2025.1): a bootable static `.pdi`,
  uncompressed partial `.pdi` files and 1–3 partitions. See `docs/pynq-pr/vd100`.
- pynq-pr: `noc_interconnect: true` (Versal) routes partition and DMA streams over the NoC instead of the
  AXI4-Stream switch. Example: `vision/pr_vd100_noc.yaml`.
- pynq-pr runtime on Versal: `Overlay("<project>.pdi")` attaches to the static design that booted, and
  the PLM loads partials from DDR over IPI (3.8 ms for a 9 MB partial on the VD100).

### Changed
- pynq-pr: a partial load that fails or is interrupted leaves its partition decoupled (it may be partly
  configured) instead of reconnecting it; the next successful load reconnects it.
- pynq-pr boards name their family and tested Vivado release (`family`, `vivado` in `boards.py`); the build
  warns when another release runs it. A board may list explicit floorplan `layouts` instead of leaving the
  split to the floorplanner, and `pynq-pr validate` checks the partition count against them.
- `reconfiguration_method: icap` is rejected for boards without an ICAP.
- `pynq-pr build -j/--jobs` sets the number of parallel Vivado runs (default 16, as before).
- `pynq-pr build` stops at the block design when a module pin is not connected to its partition boundary,
  instead of implementing an empty partition, and names the interface a module lacks.

### Fixed
- `pynq-pr build` exits non-zero when Vivado fails.

## 0.2.0 (2026-10-06)

### Changed
- cocotbpynq and pynq-pr live in one repository and share one version. pynq-pr moved here from `watcag/pynq-pr`.
- pynq-pr's base install is board-safe: it needs only PyYAML. Simulation support comes from the `sim` extra (`pip install "pynq-pr[sim]"`).
- pynq-pr uses cocotbpynq's public API: `cocotbpynq.pr` exports `PRSystem`, and `PRCocotbRunner` takes `hwh_alias`.
- The ICAP primitive comes from the board definition. Adding a board means adding an entry in `boards.py` and `scripts/ps_<board>.tcl`.
- Vivado versions other than the tested 2022.2 warn instead of stopping the build. 2022.1 is still rejected.
- cocotbpynq is published on PyPI again (`pip install cocotbpynq`). pynq-pr stays on GitHub Releases until it has a license.

### Removed
- `pynq_pr/floorplan_strips.py`, which nothing used.

## cocotbpynq 0.1.0, pynq-pr 0.1.1 (2026-09-30)

- cocotb 2.x support (tested on 2.0.1 and 2.1.0, Python 3.10–3.14).
- Swap-aware partial-reconfiguration co-simulation (`cocotbpynq.pr`), used by pynq-pr and the FPL 2026 paper.
- Fixed:
  - spurious `Write Error ... 0b0` messages;
  - PR simulation stalling on machines with fewer cores than simulation processes;
  - test runners exiting 0 when tests failed;
  - files missing from the wheels.
- Releases are distributed through GitHub Releases. PyPI still has cocotbpynq 0.0.3.

## cocotbpynq 0.0.3 (2025-09-01)

- Version described in the FPL 2025 paper. Requires `cocotb<2`.
