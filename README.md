# cocotbpynq and pynq-pr

Simulate and deploy PYNQ applications, including partial reconfiguration (DFX), from Python.

This repository holds two packages, released together under one version:

| Package | What it does | Where it runs |
|---|---|---|
| [cocotbpynq](packages/cocotbpynq/) | Runs unmodified PYNQ host code (`Overlay`, `MMIO`, DMA) against your RTL in a cocotb/Verilator simulation, including swap-aware partial-reconfiguration co-simulation | host |
| [pynq-pr](packages/pynq-pr/) | Generates a Vivado DFX design and partial bitstreams from one YAML file, simulates module swaps (with cocotbpynq), and loads partial bitstreams on the board | host (build, sim) and PYNQ board (runtime) |

## Which one do I need?

- **Simulate PYNQ host code against RTL:** cocotbpynq.
- **Build, simulate and run partial-reconfiguration designs:** pynq-pr with the `sim` extra on the host, plain pynq-pr on the board.
- **Swap partial bitstreams of your own Vivado DFX design on a board:** neither. Upstream PYNQ's `Overlay.pr_download` does that.

## Install

Releases are published on [GitHub Releases](https://github.com/watcag/cocotbpynq/releases) (PyPI is not updated yet; its `cocotbpynq` is the old 0.0.3). Replace `0.2.0` with the release you want. Simulation also needs Verilator 5.036+; the `verilator` wheel from PyPI works and is found automatically.

```sh
REL=https://github.com/watcag/cocotbpynq/releases/expanded_assets/v0.2.0

# host, co-simulation only
pip install "cocotbpynq==0.2.0" verilator --find-links $REL

# host, partial-reconfiguration build flow and simulation
pip install "pynq-pr[sim]==0.2.0" verilator --find-links $REL

# PYNQ board (in the PYNQ venv): runtime only, does not touch pynq or numpy
pip install "pynq-pr==0.2.0" --find-links $REL
```

Offline board: download `pynq_pr-0.2.0-py3-none-any.whl` from the release page, copy it to the board and run `pip install --no-deps pynq_pr-0.2.0-py3-none-any.whl`.

From a clone (to run the examples):

```sh
git clone https://github.com/watcag/cocotbpynq.git && cd cocotbpynq
pip install ./packages/cocotbpynq "./packages/pynq-pr[sim,examples]" verilator
```

For development, install both packages in editable mode: `pip install -e packages/cocotbpynq -e "packages/pynq-pr[sim,examples]"`.

## Repository layout

```
packages/cocotbpynq/   cocotbpynq package (src/, pyproject.toml, README)
packages/pynq-pr/      pynq-pr package
examples/cocotbpynq/   partial-reconfiguration co-simulation examples
examples/pynq-pr/      DFX examples: build, simulate, deploy
docs/pynq-pr/          tutorial, KV260 notes, common errors
scripts/               release tooling (bump.py, version and wheel checks)
```

## Releasing

Both packages share one version. `python scripts/bump.py X.Y.Z` sets it, then a `vX.Y.Z` tag on `main` makes CI build both packages and publish a GitHub Release with the wheels.

## Papers

- “Cocotb-Pynq: Co-simulating Python+RTL Applications Targeting Pynq Platforms with Cocotb,” G. Lusby and N. Kapre, FPL 2025. [Paper](https://nachiket.github.io/publications/cocotb-pynq_fpl-2025.pdf)
- “Cocotb-PYNQ-PR: From Co-Simulation to Deployment, A Unified DFX Framework for PYNQ,” E. Guevara, C. Sharma, G. Lusby and N. Kapre, FPL 2026. [Paper](https://nachiket.github.io/publications/cocotb-pynq-pr_fpl-2026.pdf)

See `CITATION.cff` for citation details.
