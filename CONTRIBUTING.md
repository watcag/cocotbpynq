# Contributing

## Setup

```sh
git clone https://github.com/watcag/cocotbpynq.git && cd cocotbpynq
python3 -m venv .venv && . .venv/bin/activate
pip install -e packages/cocotbpynq -e "packages/pynq-pr[sim,examples]" verilator pytest
```

Check that it works:

```sh
pytest tests
python -m cocotbpynq.sample
(cd examples/pynq-pr/add_sub && pynq-pr sim -c pr_z1.yaml --test pr_test.py -f)
```

## Workflow

- `main` is always installable and green. Never push to it directly.
- Work on a short-lived branch (days, not months), open a pull request, wait for CI, then **squash-merge** and delete the branch.
- Keep pull requests small and about one thing.
- Users install release tags, never branches.
- Add a line to `CHANGELOG.md` under *Unreleased* for anything a user would notice.

## Where code goes

| Package | Contains | Must not |
|---|---|---|
| `packages/cocotbpynq` | PYNQ-API co-simulation (`Overlay`, `MMIO`, DMA) and the generic swap-aware PR simulation engine (`cocotbpynq.pr`) | need Vivado or board-specific code |
| `packages/pynq-pr` | DFX build flow (YAML → Tcl → Vivado), board definitions, board runtime (`pynq_pr.overlay`), the `pynq-pr` CLI | add base dependencies beyond PyYAML: the base install runs on PYNQ boards. Simulation dependencies go in the `sim` extra |

pynq-pr may use cocotbpynq's public API (`cocotbpynq`, `cocotbpynq.pr`), never its private modules (`cocotbpynq._pr_engine`).

## Tests

- The examples are the end-to-end tests. CI runs each one from the built wheels, and each example must `assert` its results, not just print them.
- Only add a test that fails when the behaviour it guards is broken. Check this by breaking the code once before committing the test.
- `tests/` holds the fast checks that need no simulator (`pytest tests`).

## Adding a board

1. Add an entry to `BOARDS` in `packages/pynq-pr/src/pynq_pr/boards.py`. It needs the part, the board part, the ICAP primitive (`ICAPE2` for Zynq-7000, `ICAPE3` for Zynq UltraScale+), the clock regions, the reconfigurable regions and the pblock resources. Copy the closest existing board.
2. Add `packages/pynq-pr/src/pynq_pr/scripts/ps_<board>.tcl`, which sets up the processing system. Copy the closest existing one.
3. Run `pytest tests`. It checks that every board is complete and can floorplan 1–4 partitions.
4. On a lab machine: run `pynq-pr build` for `examples/pynq-pr/add_sub` with the new board, then run it on the board.
5. Add the board to the table in `packages/pynq-pr/README.md`.

A board with a new kind of processing system may also need changes in cocotbpynq's HWH handling.

## Releasing

Both packages share one version.

1. On a branch, run `python scripts/bump.py X.Y.Z` and move the *Unreleased* changelog entries under `X.Y.Z`. Open a PR and squash-merge it once CI is green.
2. For a minor release (`X.Y.0`), run the hardware smoke test first: install pynq-pr on a Z1 and a KV260, run `examples/pynq-pr/add_sub`, and check that `pip list` still shows the image's `pynq` and `numpy`.
3. Tag the merged commit and push the tag. CI builds both packages, publishes a GitHub Release with the wheels, and uploads cocotbpynq to **TestPyPI** for release candidates (`X.Y.ZrcN`, a dry run) or to **PyPI** for final releases. pynq-pr is uploaded too once the repository variable `PUBLISH_PYNQ_PR_TO_PYPI` is `true` (after it has a license):
   ```sh
   git tag -a vX.Y.Z -m "X.Y.Z" origin/main && git push origin vX.Y.Z
   ```
4. Run `python scripts/bump.py X.Y.(Z+1).dev0` in a follow-up PR, so `main` never reports a released version.
