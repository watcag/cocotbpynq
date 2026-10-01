"""
Video pipeline PR example — 6 reconfigurable stages, 4 RMs each, 4,096
possible pipeline configurations.

Pixel format: RGB888 packed into u32 (low 24 bits, top byte zero):
    pixel = (R << 16) | (G << 8) | B

The image is 64x64 = 4096 pixels, streamed in raster order through the
configured chain. The transformed image returns on the first stage's
DMA recv channel and is saved as a binary .ppm so it can be opened in
any image viewer.

Each scenario:
  - Configures the requested partition variants via Overlay.pr_download
  - Programs the AXI-Stream switch via overlay.chain(...)
  - Streams the synthetic 64x64 test image through
  - Verifies pixel-exact match against a numpy reference
  - Saves the result image to out/scenario_<N>_<name>.ppm

The same script runs on a PYNQ board (with pynq-pr) and in the
cocotbpynq simulator (via the synctest decorator).
"""
import os
from pathlib import Path

import numpy as np

COCOTB_IS_RUNNING = "COCOTB_SYS_ARGV" in os.environ

if not COCOTB_IS_RUNNING:
    from pynq import Overlay, allocate
else:
    import cocotbpynq
    from cocotbpynq import Overlay, allocate


H = 128
W = 128
N_PIXELS = H * W

OUT_DIR = Path(__file__).resolve().parent / "out"


# ───────────────────────── synthetic input image ──────────────────────────

def make_test_pattern():
    """Real H×W RGB image. Loads matplotlib's bundled Grace Hopper photo,
    resizes to (W, H), packs RGB888 into uint32 (low 24 bits)."""
    from PIL import Image
    import matplotlib.cbook as cbook
    src = Path(cbook.__file__).parent / "mpl-data" / "sample_data" / "grace_hopper.jpg"
    im = Image.open(src).convert("RGB").resize((W, H), Image.LANCZOS)
    arr = np.asarray(im, dtype=np.uint32)
    return (arr[..., 0] << 16) | (arr[..., 1] << 8) | arr[..., 2]


def u32_to_rgb(img_u32):
    R = ((img_u32 >> 16) & 0xFF).astype(np.uint8)
    G = ((img_u32 >>  8) & 0xFF).astype(np.uint8)
    B = ( img_u32        & 0xFF).astype(np.uint8)
    return R, G, B


def rgb_to_u32(R, G, B):
    return ((R.astype(np.uint32) & 0xFF) << 16) \
         | ((G.astype(np.uint32) & 0xFF) <<  8) \
         |  (B.astype(np.uint32) & 0xFF)


def save_ppm(img_u32, path):
    """Save 64x64 RGB image (u32-packed) as a binary P6 PPM."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    R, G, B = u32_to_rgb(img_u32)
    rgb = np.dstack([R, G, B]).astype(np.uint8)
    with open(path, "wb") as f:
        f.write(f"P6\n{W} {H}\n255\n".encode())
        f.write(rgb.tobytes())


# ───────────────────── numpy reference transforms ────────────────────────

def ref_color_identity(img):
    return img.copy()

def ref_color_grayscale(img):
    R, G, B = u32_to_rgb(img)
    y = ((77 * R.astype(np.uint32) + 150 * G.astype(np.uint32) + 29 * B.astype(np.uint32)) >> 8).astype(np.uint8)
    return rgb_to_u32(y, y, y)

def _sat(x):
    return np.clip(x, 0, 255).astype(np.uint8)

def ref_color_sepia(img):
    R, G, B = u32_to_rgb(img)
    R32, G32, B32 = R.astype(np.int32), G.astype(np.int32), B.astype(np.int32)
    Rn = (99 * R32 + 196 * G32 +  47 * B32) >> 8
    Gn = (87 * R32 + 175 * G32 +  42 * B32) >> 8
    Bn = (68 * R32 + 137 * G32 +  33 * B32) >> 8
    return rgb_to_u32(_sat(Rn), _sat(Gn), _sat(Bn))

def ref_color_invert(img):
    R, G, B = u32_to_rgb(img)
    return rgb_to_u32(255 - R, 255 - G, 255 - B)

def ref_tone_identity(img):
    return img.copy()

def ref_tone_brighten(img):
    R, G, B = u32_to_rgb(img)
    return rgb_to_u32(_sat(R.astype(np.int32) + 64),
                      _sat(G.astype(np.int32) + 64),
                      _sat(B.astype(np.int32) + 64))

def ref_tone_darken(img):
    R, G, B = u32_to_rgb(img)
    return rgb_to_u32(_sat(R.astype(np.int32) - 64),
                      _sat(G.astype(np.int32) - 64),
                      _sat(B.astype(np.int32) - 64))

def ref_tone_threshold(img):
    R, G, B = u32_to_rgb(img)
    y = (77 * R.astype(np.uint32) + 150 * G.astype(np.uint32) + 29 * B.astype(np.uint32)) >> 8
    out = np.where(y > 128, 0x00FFFFFF, 0x00000000).astype(np.uint32)
    return out

def ref_palette_identity(img):
    return img.copy()

def ref_palette_red_only(img):
    R, _, _ = u32_to_rgb(img)
    return rgb_to_u32(R, np.zeros_like(R), np.zeros_like(R))

def ref_palette_bw_dither(img):
    # cnt advances per AXIS handshake (= per pixel) in raster order,
    # 2-bit modulo with reset on TLAST (= end of frame).
    R, G, B = u32_to_rgb(img)
    y_flat = ((77 * R.astype(np.uint32) + 150 * G.astype(np.uint32) + 29 * B.astype(np.uint32)) >> 8).flatten()
    thresh_table = np.array([64, 192, 128, 0], dtype=np.uint32)
    cnt = np.arange(N_PIXELS, dtype=np.uint32) % 4
    thresh = thresh_table[cnt]
    out_flat = np.where(y_flat > thresh, 0x00FFFFFF, 0x00000000).astype(np.uint32)
    return out_flat.reshape(H, W)

def ref_palette_retro_4bit(img):
    R, G, B = u32_to_rgb(img)
    return rgb_to_u32(R & 0xF0, G & 0xF0, B & 0xF0)

def ref_stylize_identity(img):
    return img.copy()

def ref_stylize_posterize(img):
    R, G, B = u32_to_rgb(img)
    return rgb_to_u32(R & 0xF8, G & 0xF8, B & 0xF8)

def ref_stylize_pixelate(img):
    out = np.zeros_like(img)
    for y in range(H):
        for x in range(W):
            sx = x & ~1
            sy = y & ~1
            out[y, x] = img[sy, sx]
    return out

def ref_stylize_vignette(img):
    R, G, B = u32_to_rgb(img)
    out = np.zeros_like(img)
    c = W // 2
    d1 = (W * W) >> 6   # W^2/64
    d2t = (W * W) >> 4  # W^2/16
    d3 = (W * W) >> 3   # W^2/8
    d4 = (W * W) >> 2   # W^2/4
    for y in range(H):
        for x in range(W):
            d2 = (x - c) ** 2 + (y - c) ** 2
            if   d2 <  d1:  gain = 255
            elif d2 <  d2t: gain = 200
            elif d2 <  d3:  gain = 144
            elif d2 <  d4:  gain =  88
            else:           gain =  32
            rn = (int(R[y, x]) * gain) >> 8
            gn = (int(G[y, x]) * gain) >> 8
            bn = (int(B[y, x]) * gain) >> 8
            out[y, x] = (rn << 16) | (gn << 8) | bn
    return out

def ref_finalize_identity(img):
    return img.copy()

def ref_finalize_clamp_tv(img):
    R, G, B = u32_to_rgb(img)
    R = np.clip(R, 16, 240)
    G = np.clip(G, 16, 240)
    B = np.clip(B, 16, 240)
    return rgb_to_u32(R, G, B)

def ref_finalize_gain_1p5x(img):
    R, G, B = u32_to_rgb(img)
    return rgb_to_u32(_sat((R.astype(np.uint32) * 384) >> 8),
                      _sat((G.astype(np.uint32) * 384) >> 8),
                      _sat((B.astype(np.uint32) * 384) >> 8))

_GAMMA_LUT = np.array(
    [0, 64, 91, 111, 128, 142, 155, 167, 179, 189, 199, 209, 218, 227, 236, 245],
    dtype=np.uint8,
)
def ref_finalize_gamma_lut(img):
    R, G, B = u32_to_rgb(img)
    return rgb_to_u32(_GAMMA_LUT[R >> 4], _GAMMA_LUT[G >> 4], _GAMMA_LUT[B >> 4])


# 3x3 spatial — output is shifted by (+1 col, +1 row) in the output stream.
# When the RM accepts input pixel (col, row), it emits the filtered value
# centered at (col-1, row-1) if (col>=2 and row>=2), else passes the input
# through unchanged.
def _spatial_emit(img_in, kernel_fn):
    out = img_in.copy()
    for row in range(2, H):
        for col in range(2, W):
            cx = col - 1
            cy = row - 1
            out[row, col] = kernel_fn(img_in, cx, cy)
    return out

def _gather3(img, cx, cy):
    R, G, B = u32_to_rgb(img)
    r = R[cy-1:cy+2, cx-1:cx+2].astype(np.int32)
    g = G[cy-1:cy+2, cx-1:cx+2].astype(np.int32)
    b = B[cy-1:cy+2, cx-1:cx+2].astype(np.int32)
    return r, g, b

def ref_spatial_identity(img):
    return img.copy()

def ref_spatial_blur33(img):
    kw = np.array([[1,2,1],[2,4,2],[1,2,1]], dtype=np.int32)
    def k(img, cx, cy):
        r, g, b = _gather3(img, cx, cy)
        rs = int((r * kw).sum() // 16)
        gs = int((g * kw).sum() // 16)
        bs = int((b * kw).sum() // 16)
        return (rs << 16) | (gs << 8) | bs
    return _spatial_emit(img, k)

def ref_spatial_sharpen33(img):
    def k(img, cx, cy):
        r, g, b = _gather3(img, cx, cy)
        def one(p):
            s = 5*int(p[1,1]) - int(p[0,1]) - int(p[1,0]) - int(p[1,2]) - int(p[2,1])
            return int(np.clip(s, 0, 255))
        return (one(r) << 16) | (one(g) << 8) | one(b)
    return _spatial_emit(img, k)

def ref_spatial_edge33(img):
    def k(img, cx, cy):
        r, g, b = _gather3(img, cx, cy)
        def one(p):
            gx = (int(p[0,2]) + 2*int(p[1,2]) + int(p[2,2])) - (int(p[0,0]) + 2*int(p[1,0]) + int(p[2,0]))
            mag = abs(gx)
            return min(mag, 255)
        return (one(r) << 16) | (one(g) << 8) | one(b)
    return _spatial_emit(img, k)


# Per-partition variant → reference function
REF = {
    "color_identity":   ref_color_identity,
    "color_grayscale":  ref_color_grayscale,
    "color_sepia":      ref_color_sepia,
    "color_invert":     ref_color_invert,
    "spatial_identity":  ref_spatial_identity,
    "spatial_blur33":    ref_spatial_blur33,
    "spatial_sharpen33": ref_spatial_sharpen33,
    "spatial_edge33":    ref_spatial_edge33,
    "tone_identity":   ref_tone_identity,
    "tone_brighten":   ref_tone_brighten,
    "tone_darken":     ref_tone_darken,
    "tone_threshold":  ref_tone_threshold,
    "palette_identity":   ref_palette_identity,
    "palette_red_only":   ref_palette_red_only,
    "palette_bw_dither":  ref_palette_bw_dither,
    "palette_retro_4bit": ref_palette_retro_4bit,
    "stylize_identity":   ref_stylize_identity,
    "stylize_posterize":  ref_stylize_posterize,
    "stylize_pixelate":   ref_stylize_pixelate,
    "stylize_vignette":   ref_stylize_vignette,
    "finalize_identity":  ref_finalize_identity,
    "finalize_clamp_tv":  ref_finalize_clamp_tv,
    "finalize_gain_1p5x": ref_finalize_gain_1p5x,
    "finalize_gamma_lut": ref_finalize_gamma_lut,
}


# ────────────────────────── DMA helpers ──────────────────────────────────

def stream(dma, x_buf, y_buf):
    y_buf[:] = 0
    dma.recvchannel.transfer(y_buf)
    dma.sendchannel.transfer(x_buf)
    dma.sendchannel.wait()
    dma.recvchannel.wait()


def apply_chain(out_img, in_img, parts_and_rms):
    """Apply numpy refs in pipeline order."""
    cur = in_img.copy()
    for (_part, rm) in parts_and_rms:
        cur = REF[rm](cur)
    out_img[:] = cur


def reconfigure(overlay, parts_and_rms):
    for part, rm in parts_and_rms:
        overlay.pr_download(part, rm)


# ────────────────────────── test scenarios ──────────────────────────────

def scenario(idx, name, overlay, x_alloc, y_alloc, in_img, parts_and_rms):
    """Run one scenario: reconfigure, chain, stream, verify, save."""
    print(f"[scenario {idx}] {name}")
    print(f"    chain: {[p for (p, _) in parts_and_rms]}")
    print(f"    rms  : {[r for (_, r) in parts_and_rms]}")

    reconfigure(overlay, parts_and_rms)
    dma = overlay.chain([p for (p, _) in parts_and_rms])

    x_alloc[:] = in_img.flatten().astype(np.uint32)
    stream(dma, x_alloc, y_alloc)

    got = np.asarray(y_alloc, dtype=np.uint32).reshape(H, W)
    expected = np.zeros_like(in_img)
    apply_chain(expected, in_img, parts_and_rms)

    save_ppm(got, OUT_DIR / f"scenario_{idx}_{name}.ppm")
    save_ppm(expected, OUT_DIR / f"scenario_{idx}_{name}_ref.ppm")

    if not np.array_equal(got, expected):
        diff = (got.astype(np.int64) - expected.astype(np.int64))
        n_diff = int(np.count_nonzero(diff))
        first = int(np.argmax(diff != 0))
        raise AssertionError(
            f"scenario {idx} ({name}): {n_diff}/{N_PIXELS} pixels differ; "
            f"first mismatch at index {first}: got 0x{int(got.flatten()[first]):08x} "
            f"vs expected 0x{int(expected.flatten()[first]):08x}"
        )
    print(f"    PASS — saved out/scenario_{idx}_{name}.ppm")


def main(dut=None):
    overlay = Overlay("design.bit")

    x_alloc = allocate(shape=(N_PIXELS,), dtype=np.uint32)
    y_alloc = allocate(shape=(N_PIXELS,), dtype=np.uint32)

    in_img = make_test_pattern()
    save_ppm(in_img, OUT_DIR / "input.ppm")

    # 1) All-identity — sanity check, output equals input.
    scenario(1, "all_identity", overlay, x_alloc, y_alloc, in_img, [
        ("rp_color",    "color_identity"),
        ("rp_spatial",  "spatial_identity"),
        ("rp_tone",     "tone_identity"),
        ("rp_palette",  "palette_identity"),
        ("rp_stylize",  "stylize_identity"),
        ("rp_finalize", "finalize_identity"),
    ])

    # 2) Single stage — subset routing.
    scenario(2, "grayscale_only", overlay, x_alloc, y_alloc, in_img, [
        ("rp_color", "color_grayscale"),
    ])

    # 3) Color + spatial — 3x3 line buffer plus chain.
    scenario(3, "grayscale_edge", overlay, x_alloc, y_alloc, in_img, [
        ("rp_color",   "color_grayscale"),
        ("rp_spatial", "spatial_edge33"),
    ])

    # 4) 3-stage chain.
    scenario(4, "sepia_bright_pixelate", overlay, x_alloc, y_alloc, in_img, [
        ("rp_color",   "color_sepia"),
        ("rp_tone",    "tone_brighten"),
        ("rp_stylize", "stylize_pixelate"),
    ])

    # 5) Full 6-stage — the signature scenario.
    scenario(5, "full_six_stage", overlay, x_alloc, y_alloc, in_img, [
        ("rp_color",    "color_sepia"),
        ("rp_spatial",  "spatial_blur33"),
        ("rp_tone",     "tone_brighten"),
        ("rp_palette",  "palette_red_only"),
        ("rp_stylize",  "stylize_posterize"),
        ("rp_finalize", "finalize_gamma_lut"),
    ])

    # 6) Order matters — same RMs, swapped chain order, different results.
    scenario(6, "order_color_then_spatial", overlay, x_alloc, y_alloc, in_img, [
        ("rp_color",   "color_sepia"),
        ("rp_spatial", "spatial_edge33"),
    ])
    out_a = np.asarray(y_alloc, dtype=np.uint32).reshape(H, W).copy()

    scenario(6, "order_spatial_then_color", overlay, x_alloc, y_alloc, in_img, [
        ("rp_spatial", "spatial_edge33"),
        ("rp_color",   "color_sepia"),
    ])
    out_b = np.asarray(y_alloc, dtype=np.uint32).reshape(H, W).copy()

    if np.array_equal(out_a, out_b):
        raise AssertionError("scenario 6: chain order did not affect output (expected different)")
    print(f"[scenario 6] order_matters: PASS (chain order produces different outputs)")

    # 7) Mid-test reconfiguration — change one RM, re-process, verify
    print("[scenario 7] mid_test_reconfig")
    chain_def = [("rp_color", "color_grayscale"), ("rp_spatial", "spatial_blur33")]
    reconfigure(overlay, chain_def)
    dma = overlay.chain([p for (p, _) in chain_def])
    x_alloc[:] = in_img.flatten().astype(np.uint32)
    stream(dma, x_alloc, y_alloc)
    pre = np.asarray(y_alloc, dtype=np.uint32).reshape(H, W).copy()
    save_ppm(pre, OUT_DIR / "scenario_7_pre_reconfig.ppm")

    print("    reconfiguring rp_spatial: spatial_blur33 → spatial_edge33")
    overlay.pr_download("rp_spatial", "spatial_edge33")

    stream(dma, x_alloc, y_alloc)
    post = np.asarray(y_alloc, dtype=np.uint32).reshape(H, W).copy()
    save_ppm(post, OUT_DIR / "scenario_7_post_reconfig.ppm")

    expected_post = ref_spatial_edge33(ref_color_grayscale(in_img))
    if not np.array_equal(post, expected_post):
        raise AssertionError("scenario 7: post-reconfig output != edge33 reference")
    if np.array_equal(pre, post):
        raise AssertionError("scenario 7: pre/post identical (reconfig had no effect)")
    print("    PASS — pre != post, post matches numpy edge reference")

    # 8) Subset skip — only 2 of 6 stages active.
    scenario(8, "subset_tone_finalize", overlay, x_alloc, y_alloc, in_img, [
        ("rp_tone",     "tone_brighten"),
        ("rp_finalize", "finalize_gamma_lut"),
    ])

    print("\nAll scenarios PASS. Output images in out/ as .ppm files.")


if __name__ == "__main__":
    main()
elif COCOTB_IS_RUNNING:
    main = cocotbpynq.synctest(main)
