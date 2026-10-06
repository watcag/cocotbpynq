# Changelog

Both packages (cocotbpynq and pynq-pr) are released together under one version from 0.2.0 onwards.

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
