import os
import numpy as np
import time

COCOTB_IS_RUNNING = "COCOTB_SYS_ARGV" in os.environ

if not COCOTB_IS_RUNNING:
    import argparse
    from pynq import allocate
    from overlay import Overlay
else:
    import cocotbpynq
    from pynq_pr.overlay_sim import Overlay, allocate

PARTITION = "attn"
L = 32
D = 64
RNG_SEED = 722
NUM_TESTS = 2
VALUE_MIN = -4
VALUE_MAX = 5

FP_BITS  = 30
MAX_BITS = 30
OUT_BITS = 6
QB       = np.int32(1216)
QC       = np.int32(563942)
QLN2     = np.int32(-312)
QLN2_INV = np.int32(-3441481)
SREQ     = np.int32(62388177)
NEG_MASK = np.int32(-1048576)


def exp_model(qin):
    fp_mul  = np.int64(qin) * np.int64(QLN2_INV)
    z       = fp_mul >> FP_BITS
    qp      = np.int64(qin) - np.int64(z) * np.int64(QLN2)
    ql      = (qp + np.int64(QB)) * qp + np.int64(QC)
    z_shift = np.minimum(z, 2 * 32)
    return np.where(z_shift >= 64, 0, ql >> np.minimum(z_shift, 63)).astype(np.int32)


def softmax_row(values):
    qin    = np.array(values, dtype=np.int32)
    qmax   = np.max(qin)
    qhat   = qin - qmax
    qexp   = exp_model(qhat)
    qreq64 = np.int64(qexp) * np.int64(SREQ)
    qreq   = np.round(qreq64.astype(np.float64) / (2.0 ** FP_BITS)).astype(np.int32)
    qsum   = np.sum(qreq, dtype=np.int32)
    factor = np.int32(np.floor((1 << MAX_BITS) / qsum))
    return np.uint8((qreq * factor) >> (MAX_BITS - OUT_BITS)).astype(np.int32)


def reference_qk(Q, K):
    """S = Q @ K^T (no causal mask — hardware applies it in sfm stage)."""
    return np.matmul(Q.astype(np.int32), K.T.astype(np.int32))


def reference_sfm(S):
    """Causal mask then row-wise integer softmax. Returns int32 (L, L)."""
    upper = np.triu(np.ones((L, L), dtype=bool), k=1)
    S_masked = np.where(upper, NEG_MASK, S)
    return np.stack([softmax_row(S_masked[i]) for i in range(L)])


def reference_pv(P, V):
    """O = P @ V. Returns int32 (L, D)."""
    return np.matmul(P.astype(np.int32), V.astype(np.int32))


def reference_attention(Q, K, V):
    """Full staged reference: runs qk, sfm, pv and returns O (L*D flattened)."""
    S = reference_qk(Q, K)
    P = reference_sfm(S)
    O = reference_pv(P, V)
    return O.reshape(-1)


def _free(*bufs):
    for b in bufs:
        if hasattr(b, "freebuffer"):
            b.freebuffer()


def dma_qk(dma, Q, K):
    """Send Q[L*D] then K^T[D*L], receive S[L*L] int32."""
    KT = K.T.copy()
    q_buf  = allocate(shape=L * D,  dtype=np.int32)
    kt_buf = allocate(shape=D * L,  dtype=np.int32)
    s_buf  = allocate(shape=L * L,  dtype=np.int32)
    np.copyto(q_buf,  Q.reshape(-1).astype(np.int32))
    np.copyto(kt_buf, KT.reshape(-1).astype(np.int32))
    dma.recvchannel.transfer(s_buf)
    dma.sendchannel.transfer(q_buf);  dma.sendchannel.wait()
    dma.sendchannel.transfer(kt_buf); dma.sendchannel.wait()
    dma.recvchannel.wait()
    S = np.array(s_buf, dtype=np.int32).reshape(L, L)
    _free(q_buf, kt_buf, s_buf)
    return S


def dma_sfm(dma, S):
    """Send S[L*L] int32, receive P[L*L] int8-in-int32."""
    s_buf = allocate(shape=L * L, dtype=np.int32)
    p_buf = allocate(shape=L * L, dtype=np.int32)
    np.copyto(s_buf, S.reshape(-1))
    dma.recvchannel.transfer(p_buf)
    dma.sendchannel.transfer(s_buf); dma.sendchannel.wait()
    dma.recvchannel.wait()
    P = np.array(p_buf, dtype=np.int32).reshape(L, L)
    _free(s_buf, p_buf)
    return P


def dma_pv(dma, P, V):
    """Send P[L*L] int8, then V[L*D] int8, receive O[L*D] int32."""
    p_buf = allocate(shape=L * L,  dtype=np.int32)
    v_buf = allocate(shape=L * D,  dtype=np.int32)
    o_buf = allocate(shape=L * D,  dtype=np.int32)
    np.copyto(p_buf, P.reshape(-1))
    np.copyto(v_buf, V.reshape(-1).astype(np.int32))
    dma.recvchannel.transfer(o_buf)
    dma.sendchannel.transfer(p_buf); dma.sendchannel.wait()
    dma.sendchannel.transfer(v_buf); dma.sendchannel.wait()
    dma.recvchannel.wait()
    O = np.array(o_buf, dtype=np.int32).reshape(L, D)
    _free(p_buf, v_buf, o_buf)
    return O


def run_staged_attention(ol, Q, K, V, ext, icap, verbose=False):
    """
    Run one full attention forward pass using three PR swaps.
    Verifies intermediate S and P against reference as well as final O.
    Returns True if all three stages match.
    """
    ref_S = reference_qk(Q, K)
    ref_P = reference_sfm(ref_S)
    ref_O = reference_pv(ref_P, V)

    all_pass = True
    t_reconfig = []
    t_compute  = []

    # --- Stage 1: QK matmul ---
    t0 = time.monotonic()
    ol.pr_download(PARTITION, f"{PARTITION}_qk{ext}", icap=icap)
    t_reconfig.append(time.monotonic() - t0)

    dma = ol.chain([PARTITION])
    t0 = time.monotonic()
    hw_S = dma_qk(dma, Q, K)
    t_compute.append(time.monotonic() - t0)

    stage_pass = np.array_equal(hw_S, ref_S)
    if not stage_pass:
        all_pass = False
        if verbose:
            diff = np.where(hw_S != ref_S)
            print(f"      QK FAIL: {len(diff[0])} mismatches")
    elif verbose:
        print(f"      QK PASS  reconfig={t_reconfig[-1]*1e3:.1f}ms  compute={t_compute[-1]*1e3:.1f}ms")

    # --- Stage 2: softmax ---
    t0 = time.monotonic()
    ol.pr_download(PARTITION, f"{PARTITION}_sfm{ext}", icap=icap)
    t_reconfig.append(time.monotonic() - t0)

    dma = ol.chain([PARTITION])
    t0 = time.monotonic()
    hw_P = dma_sfm(dma, hw_S)
    t_compute.append(time.monotonic() - t0)

    stage_pass = np.array_equal(hw_P, ref_P)
    if not stage_pass:
        all_pass = False
        if verbose:
            diff = np.where(hw_P != ref_P)
            print(f"      SFM FAIL: {len(diff[0])} mismatches")
    elif verbose:
        print(f"      SFM PASS  reconfig={t_reconfig[-1]*1e3:.1f}ms  compute={t_compute[-1]*1e3:.1f}ms")

    # --- Stage 3: PV matmul ---
    t0 = time.monotonic()
    ol.pr_download(PARTITION, f"{PARTITION}_pv{ext}", icap=icap)
    t_reconfig.append(time.monotonic() - t0)

    dma = ol.chain([PARTITION])
    t0 = time.monotonic()
    hw_O = dma_pv(dma, hw_P, V)
    t_compute.append(time.monotonic() - t0)

    stage_pass = np.array_equal(hw_O.reshape(-1), ref_O.reshape(-1))
    if not stage_pass:
        all_pass = False
        if verbose:
            diff = np.where(hw_O.reshape(-1) != ref_O.reshape(-1))[0]
            print(f"      PV FAIL: {len(diff)} mismatches")
    elif verbose:
        print(f"      PV PASS  reconfig={t_reconfig[-1]*1e3:.1f}ms  compute={t_compute[-1]*1e3:.1f}ms")

    if verbose and all_pass:
        print(f"      total_reconfig={sum(t_reconfig)*1e3:.1f}ms  total_compute={sum(t_compute)*1e3:.1f}ms")
    return all_pass


def main(dut=None):
    if COCOTB_IS_RUNNING:
        ol   = Overlay("design.bit")
        icap = False
    else:
        parser = argparse.ArgumentParser(description="Staged attention PR test")
        parser.add_argument("--project", required=True)
        parser.add_argument("--icap", action="store_true")
        args = parser.parse_args()
        ol   = Overlay(f"{args.project}.bit")
        icap = args.icap

    ext = ".bin" if icap else ".bit"
    rng = np.random.default_rng(RNG_SEED)
    all_pass = True

    for test_idx in range(NUM_TESTS):
        Q = rng.integers(VALUE_MIN, VALUE_MAX, (L, D), dtype=np.int8)
        K = rng.integers(VALUE_MIN, VALUE_MAX, (L, D), dtype=np.int8)
        V = rng.integers(VALUE_MIN, VALUE_MAX, (L, D), dtype=np.int8)
        print(f"  test{test_idx}:", flush=True)
        ok = run_staged_attention(ol, Q, K, V, ext, icap, verbose=True)
        if not ok:
            all_pass = False

    assert all_pass, "staged attention output mismatch"
    print("All tests passed!", flush=True)


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
