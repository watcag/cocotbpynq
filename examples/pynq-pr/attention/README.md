# Attention Example

Staged scaled dot-product attention over a single reconfigurable partition
`attn`. Three structurally different RMs (QK matmul, a softmax, and a PV
matmul) are swapped in and out via ICAP:

```text
[qk]   S = Q @ K^T           (32×64) @ (64×32) -> (32×32) int32
[sfm]  P = causal_softmax(S)  (32×32) int32    -> (32×32) int8
[pv]   O = P @ V             (32×32) @ (32×64) -> (32×64) int32
```

Intermediates (S, P) round-trip through DDR between stages.

| RM    | Circuit   | Input                  | Output           |
|-------|-----------|------------------------|------------------|
| `qk`  | mm_pp     | Q[32×64], K^T[64×32]  | S[32×32] int32   |
| `sfm` | softmax   | S[32×32] int32         | P[32×32] int8    |
| `pv`  | mm_pp     | P[32×32], V[32×64]    | O[32×64] int32   |

`SEQ_LEN=32` (softmax is hardwired for N=32), `HEAD_DIM=64`.

## Simulation

```bash
cd examples/pynq-pr/attention
pynq-pr sim -c pr_z1.yaml --test pr_test.py -f
```

Each stage is verified independently against an integer reference model:

```
test0:
    QK PASS   reconfig=...ms  compute=...ms
    SFM PASS  reconfig=...ms  compute=...ms
    PV PASS   reconfig=...ms  compute=...ms
```

## Build And Deploy

```bash
pynq-pr build -c pr_z1.yaml      # or pr_kv260.yaml

./deploy.sh -b z1 bits
./deploy.sh -b z1 run
./deploy.sh -b z1 all
```

`-b kv260` for the KV260. `BOARD_IP` overrides the default target address.

`deploy.sh` copies the full bitstream, HWH, all partial bitstreams for `attn`,
the board-side [`overlay.py`](../../../packages/pynq-pr/src/pynq_pr/overlay.py), and the test script.
